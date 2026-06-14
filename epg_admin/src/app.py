"""
EPG Admin Service for SFTPGo.

This module hosts a single Flask application that combines:
1. A Prometheus exporter for per-user login/staleness telemetry.
2. A lightweight HTML admin UI for customer account lifecycle operations.

Architecture summary:
- SFTPGo is the source of truth for users/groups/folders.
- ``/metrics`` is the combined scrape endpoint for custom ``sftpgo_*`` metrics and,
  optionally, native SFTPGo metrics proxied from SFTPGo telemetry.
- ``/admin/*`` routes use SFTPGo Admin API tokens issued from admin credentials
  supplied at login time.

Primary routes:
- ``GET /healthz``: exporter health based on successful SFTPGo API refresh.
- ``GET /metrics``: custom + optional merged native Prometheus exposition.
- ``GET|POST /admin/login``: login with SFTPGo admin credentials.
- ``POST /admin/logout``: revoke local in-memory session.
- ``GET /admin/users``: list users and staleness.
- ``GET /admin/files``: list files currently stored under the shared EPG root.
- ``GET|POST /admin/users/create``: create user with managed defaults.
- ``POST /admin/users/<username>/disable``: disable account.
- ``POST /admin/users/<username>/status``: enable/disable account.
- ``POST /admin/users/<username>/delete``: permanently delete account.
- ``GET|POST /admin/users/<username>/change-password``: change user password.

Key environment variables:
- ``SFTPGO_API_BASE_URL``: base URL for SFTPGo Admin API v2.
- ``SFTPGO_API_USERNAME`` / ``SFTPGO_API_PASSWORD``: exporter credentials.
- ``STALE_AFTER_HOURS``: threshold used by stale metrics and UI staleness flags.
- ``MERGE_SFTPGO_NATIVE_METRICS`` / ``SFTPGO_NATIVE_METRICS_URL``:
  controls native metrics merge behavior.
- ``EPG_ADMIN_SESSION_*``: cookie name and session lifetime.
- ``EPG_ADMIN_MANAGED_*``: managed folder/group/virtual path defaults used when
  provisioning new customer users.
- ``EPG_BUNDLE_*``: generated bundle freshness/count checks exported as
  ``epg_bundle_*`` metrics.
"""

import base64
import ipaddress
import json
import os
import secrets
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import (
    Flask,
    Response,
    flash,
    get_flashed_messages,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from prometheus_client import CollectorRegistry, Gauge, generate_latest
from waitress import serve


@dataclass
class UserSnapshot:
    """Normalized subset of SFTPGo user fields used for metric generation."""

    username: str
    status: str
    last_login_ts: float
    last_download_ts: float


@dataclass
class AdminSession:
    """In-memory admin UI session."""

    session_id: str
    username: str
    password: str
    expires_at: float


@dataclass
class DownloadSnapshot:
    """Latest successful download metadata for a customer user."""

    username: str
    last_download_ts: float
    filename: str
    file_path: str
    virtual_path: str
    file_size: int
    protocol: str
    ip: str
    successful_downloads: int


@dataclass
class LoginSnapshot:
    """Latest successful login metadata for a customer user."""

    username: str
    last_login_ts: float
    method: str
    protocol: str
    ip: str
    successful_logins: int


def now_utc_iso(ts: Optional[float] = None) -> str:
    """Format timestamp for human-readable UTC display."""
    if ts is None:
        ts = time.time()
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def parse_sftpgo_event_timestamp(value: Any) -> float:
    """Convert SFTPGo event timestamps to Unix seconds."""
    if not isinstance(value, (int, float)):
        return 0.0
    ts = float(value)
    if ts <= 0:
        return 0.0
    if ts > 1_000_000_000_000_000:
        return ts / 1_000_000_000.0
    if ts > 1_000_000_000_000:
        return ts / 1000.0
    return ts


def int_or_default(value: Any, default: int = 0) -> int:
    """Convert a value to int, returning a default for invalid input."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def download_filename(file_path: str, virtual_path: str) -> str:
    """Return the basename for a downloaded file using virtual path first."""
    return os.path.basename(virtual_path or file_path)


class SFTPGoClient:
    """SFTPGo API client with token caching and common user/group/folder operations."""

    def __init__(self, base_url: str, timeout_seconds: int, username: str = "", password: str = ""):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.username = username
        self.password = password
        self._token: Optional[str] = None
        self._token_expiry_ts: float = 0

    def set_credentials(self, username: str, password: str) -> None:
        """Update auth credentials and clear cached access token state."""
        self.username = username
        self.password = password
        self._token = None
        self._token_expiry_ts = 0

    def _build_request(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        data: Optional[bytes] = None,
    ) -> Request:
        """Construct a urllib Request object used for API calls."""
        return Request(url=url, method=method, headers=headers or {}, data=data)

    def _read_response(self, req: Request) -> tuple[int, bytes]:
        """Execute an HTTP request and return ``(status_code, body_bytes)``."""
        with urlopen(req, timeout=self.timeout_seconds) as resp:
            return int(resp.status), resp.read()

    def _ensure_token(self) -> str:
        """Return a valid bearer token, refreshing from ``/token`` when required."""
        now = time.time()
        if self._token and now < self._token_expiry_ts:
            return self._token

        if not self.username or not self.password:
            raise ValueError("Missing SFTPGo API credentials")

        creds = f"{self.username}:{self.password}".encode("utf-8")
        auth = base64.b64encode(creds).decode("ascii")
        req = self._build_request(
            f"{self.base_url}/token",
            method="GET",
            headers={"Authorization": f"Basic {auth}"},
        )
        _, raw = self._read_response(req)
        payload = json.loads(raw.decode("utf-8"))

        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise ValueError("SFTPGo token response missing access_token")

        expires_at = payload.get("expires_at")
        expiry = now + 300
        if isinstance(expires_at, (int, float)):
            expiry = float(expires_at) - 5

        self._token = token
        self._token_expiry_ts = max(now + 10, expiry)
        return token

    def _request_json(
        self,
        method: str,
        path: str,
        query: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
        allow_404: bool = False,
    ) -> Optional[Any]:
        """
        Execute a JSON request against SFTPGo with automatic token retry on 401.

        When ``allow_404`` is true, a 404 response is treated as ``None``.
        """
        token = self._ensure_token()
        qs = f"?{urlencode(query)}" if query else ""
        url = f"{self.base_url}{path}{qs}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        body: Optional[bytes] = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")

        req = self._build_request(url=url, method=method, headers=headers, data=body)
        try:
            _, raw = self._read_response(req)
        except HTTPError as exc:
            if exc.code == 401:
                self._token = None
                token = self._ensure_token()
                headers["Authorization"] = f"Bearer {token}"
                req = self._build_request(url=url, method=method, headers=headers, data=body)
                _, raw = self._read_response(req)
            elif allow_404 and exc.code == 404:
                return None
            else:
                raise

        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))

    def fetch_users(self) -> List[dict]:
        """Fetch all users from SFTPGo using paginated ``/users`` calls."""
        users: List[dict] = []
        limit = 200
        offset = 0

        while True:
            page = self._request_json("GET", "/users", query={"limit": limit, "offset": offset})
            if page is None:
                break
            if not isinstance(page, list):
                raise ValueError("Unexpected /users response type")
            users.extend(page)
            if len(page) < limit:
                break
            offset += limit

        return users

    def get_user(self, username: str) -> Optional[dict]:
        """Fetch a single user by username, returning ``None`` when not found."""
        return self._request_json("GET", f"/users/{username}", allow_404=True)

    def create_user(self, user_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create an SFTPGo user and return the created object."""
        created = self._request_json("POST", "/users", payload=user_payload)
        if not isinstance(created, dict):
            raise ValueError("Unexpected create user response")
        return created

    def update_user(self, username: str, user_payload: Dict[str, Any]) -> None:
        """Update an existing user via ``PUT /users/<username>``."""
        self._request_json("PUT", f"/users/{username}", payload=user_payload)

    def delete_user(self, username: str) -> None:
        """Delete a user via ``DELETE /users/<username>``."""
        self._request_json("DELETE", f"/users/{username}")

    def get_group(self, name: str) -> Optional[dict]:
        """Fetch a group by name, returning ``None`` when not found."""
        return self._request_json("GET", f"/groups/{name}", allow_404=True)

    def create_group(self, group_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create an SFTPGo group and return the created object."""
        created = self._request_json("POST", "/groups", payload=group_payload)
        if not isinstance(created, dict):
            raise ValueError("Unexpected create group response")
        return created

    def get_folder(self, name: str) -> Optional[dict]:
        """Fetch a virtual folder by name, returning ``None`` when not found."""
        return self._request_json("GET", f"/folders/{name}", allow_404=True)

    def create_folder(self, folder_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create a virtual folder and return the created object."""
        created = self._request_json("POST", "/folders", payload=folder_payload)
        if not isinstance(created, dict):
            raise ValueError("Unexpected create folder response")
        return created


class SFTPGoEventStore:
    """Persistent latest successful login/download state keyed by SFTPGo username."""

    def __init__(self, state_path: str):
        self.state_path = state_path
        self._lock = Lock()
        self._logins: Dict[str, LoginSnapshot] = {}
        self._downloads: Dict[str, DownloadSnapshot] = {}
        self._load()

    def _load(self) -> None:
        """Load persisted event state if present."""
        try:
            with open(self.state_path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except FileNotFoundError:
            return
        except (json.JSONDecodeError, OSError):
            return

        if not isinstance(raw, dict):
            return

        raw_users = raw.get("users", {})
        if not isinstance(raw_users, dict):
            return

        logins: Dict[str, LoginSnapshot] = {}
        downloads: Dict[str, DownloadSnapshot] = {}
        for username, item in raw_users.items():
            if not isinstance(username, str) or not isinstance(item, dict):
                continue

            login_item = item.get("login")
            if isinstance(login_item, dict):
                last_login_ts = float(login_item.get("last_login_ts", 0.0) or 0.0)
                if last_login_ts > 0:
                    logins[username] = LoginSnapshot(
                        username=username,
                        last_login_ts=last_login_ts,
                        method=str(login_item.get("method", "") or ""),
                        protocol=str(login_item.get("protocol", "") or ""),
                        ip=str(login_item.get("ip", "") or ""),
                        successful_logins=int_or_default(login_item.get("successful_logins", 0)),
                    )

            download_item = item.get("download")
            if not isinstance(download_item, dict):
                download_item = item
            last_download_ts = float(download_item.get("last_download_ts", 0.0) or 0.0)
            if last_download_ts <= 0:
                continue
            file_path = str(download_item.get("file_path", "") or "")
            virtual_path = str(download_item.get("virtual_path", "") or "")
            filename = str(download_item.get("filename", "") or "") or download_filename(file_path, virtual_path)
            downloads[username] = DownloadSnapshot(
                username=username,
                last_download_ts=last_download_ts,
                filename=filename,
                file_path=file_path,
                virtual_path=virtual_path,
                file_size=int_or_default(download_item.get("file_size", 0)),
                protocol=str(download_item.get("protocol", "") or ""),
                ip=str(download_item.get("ip", "") or ""),
                successful_downloads=int_or_default(download_item.get("successful_downloads", 0)),
            )

        self._logins = logins
        self._downloads = downloads

    def _save_locked(self) -> None:
        """Persist current state to disk using atomic replace semantics."""
        directory = os.path.dirname(self.state_path) or "."
        os.makedirs(directory, exist_ok=True)
        users: Dict[str, Dict[str, Any]] = {}
        for username, snap in sorted(self._logins.items()):
            users.setdefault(username, {})["login"] = {
                "last_login_ts": snap.last_login_ts,
                "method": snap.method,
                "protocol": snap.protocol,
                "ip": snap.ip,
                "successful_logins": snap.successful_logins,
            }
        for username, snap in sorted(self._downloads.items()):
            users.setdefault(username, {})["download"] = {
                "last_download_ts": snap.last_download_ts,
                "filename": snap.filename,
                "file_path": snap.file_path,
                "virtual_path": snap.virtual_path,
                "file_size": snap.file_size,
                "protocol": snap.protocol,
                "ip": snap.ip,
                "successful_downloads": snap.successful_downloads,
            }

        payload = {
            "updated_at": now_utc_iso(),
            "users": users,
        }
        fd, tmp_path = tempfile.mkstemp(prefix=".sftpgo-events-", suffix=".json", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, sort_keys=True)
                fh.write("\n")
            os.replace(tmp_path, self.state_path)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def login_snapshot(self) -> Dict[str, LoginSnapshot]:
        """Return a copy of the current login state."""
        with self._lock:
            return dict(self._logins)

    def download_snapshot(self) -> Dict[str, DownloadSnapshot]:
        """Return a copy of the current download state."""
        with self._lock:
            return dict(self._downloads)

    def record_login(self, username: str, method: str, protocol: str, ip: str, status: int) -> Optional[LoginSnapshot]:
        """
        Record a successful SFTPGo post-login event.

        Returns the stored snapshot, or ``None`` if the event should be ignored.
        """
        if status != 1 or not username:
            return None

        ts = time.time()
        with self._lock:
            previous = self._logins.get(username)
            successful_logins = 1
            if previous is not None:
                successful_logins = previous.successful_logins + 1

            snap = LoginSnapshot(
                username=username,
                last_login_ts=ts,
                method=method,
                protocol=protocol,
                ip=ip,
                successful_logins=successful_logins,
            )
            self._logins[username] = snap
            self._save_locked()
            return snap

    def record_download(self, event: Dict[str, Any]) -> Optional[DownloadSnapshot]:
        """
        Record a successful SFTPGo download event.

        Returns the stored snapshot, or ``None`` if the event should be ignored.
        """
        if event.get("action") != "download":
            return None
        if int_or_default(event.get("status", 0)) != 1:
            return None

        username = event.get("username")
        if not isinstance(username, str) or not username:
            return None

        ts = parse_sftpgo_event_timestamp(event.get("timestamp"))
        if ts <= 0:
            ts = time.time()

        file_path = str(event.get("path", "") or "")
        virtual_path = str(event.get("virtual_path", "") or "")
        filename = download_filename(file_path, virtual_path)
        file_size = int_or_default(event.get("file_size", 0))
        protocol = str(event.get("protocol", "") or "")
        ip = str(event.get("ip", "") or "")

        with self._lock:
            previous = self._downloads.get(username)
            successful_downloads = 1
            if previous is not None:
                successful_downloads = previous.successful_downloads + 1
                if previous.last_download_ts > ts:
                    ts = previous.last_download_ts
                    filename = previous.filename
                    file_path = previous.file_path
                    virtual_path = previous.virtual_path
                    file_size = previous.file_size
                    protocol = previous.protocol
                    ip = previous.ip

            snap = DownloadSnapshot(
                username=username,
                last_download_ts=ts,
                filename=filename,
                file_path=file_path,
                virtual_path=virtual_path,
                file_size=file_size,
                protocol=protocol,
                ip=ip,
                successful_downloads=successful_downloads,
            )
            self._downloads[username] = snap
            self._save_locked()
            return snap


class ExporterState:
    """Thread-safe in-memory cache for SFTPGo user snapshots and refresh metadata."""

    def __init__(self, client: SFTPGoClient, refresh_interval_seconds: int, event_store: SFTPGoEventStore):
        self.client = client
        self.refresh_interval_seconds = refresh_interval_seconds
        self.event_store = event_store
        self._lock = Lock()
        self._last_refresh_ts: float = 0
        self._last_success_ts: float = 0
        self._last_error: str = ""
        self._error_count: int = 0
        self._users: Dict[str, UserSnapshot] = {}

    @property
    def last_success_ts(self) -> float:
        """Unix timestamp of the last successful SFTPGo API refresh."""
        return self._last_success_ts

    @property
    def last_error(self) -> str:
        """String representation of the last refresh error, if any."""
        return self._last_error

    @property
    def error_count(self) -> int:
        """Number of refresh errors encountered since process start."""
        return self._error_count

    @property
    def users(self) -> Dict[str, UserSnapshot]:
        """Current cached user snapshot map keyed by username."""
        return self._users

    def refresh_if_needed(self) -> None:
        """Refresh cache from SFTPGo if the refresh interval has elapsed."""
        now = time.time()
        if now - self._last_refresh_ts < self.refresh_interval_seconds:
            return

        with self._lock:
            now = time.time()
            if now - self._last_refresh_ts < self.refresh_interval_seconds:
                return

            self._last_refresh_ts = now
            try:
                raw_users = self.client.fetch_users()
                users: Dict[str, UserSnapshot] = {}
                logins = self.event_store.login_snapshot()
                downloads = self.event_store.download_snapshot()
                for item in raw_users:
                    if not isinstance(item, dict):
                        continue
                    username = item.get("username")
                    if not isinstance(username, str) or not username:
                        continue
                    status = "enabled" if int(item.get("status", 0)) == 1 else "disabled"
                    last_login_ms = item.get("last_login", 0)
                    if isinstance(last_login_ms, (int, float)) and last_login_ms > 0:
                        last_login_ts = float(last_login_ms) / 1000.0
                    else:
                        last_login_ts = 0.0
                    login = logins.get(username)
                    if login is not None and login.last_login_ts > 0:
                        last_login_ts = login.last_login_ts
                    last_download_ts = downloads.get(username).last_download_ts if username in downloads else 0.0
                    users[username] = UserSnapshot(
                        username=username,
                        status=status,
                        last_login_ts=last_login_ts,
                        last_download_ts=last_download_ts,
                    )

                self._users = users
                self._last_success_ts = now
                self._last_error = ""
            except (HTTPError, URLError, ValueError, OSError) as exc:
                self._error_count += 1
                self._last_error = str(exc)


def sanitize_user_for_update(user: Dict[str, Any]) -> Dict[str, Any]:
    """Remove read-only fields from a user payload before PUT update."""
    copy = dict(user)
    for key in (
        "id",
        "has_password",
        "used_quota_size",
        "used_quota_files",
        "last_quota_update",
        "created_at",
        "updated_at",
        "last_login",
        "first_download",
        "first_upload",
        "last_password_change",
        "oidc_custom_fields",
    ):
        copy.pop(key, None)
    return copy


def create_app() -> Flask:
    """
    Application factory for the EPG Admin service.

    Creates the Flask app, wires SFTPGo/API clients, initializes in-memory session
    management, and registers metrics and admin routes.
    """
    # ------------------------------------------------------------------
    # Runtime configuration
    # ------------------------------------------------------------------
    api_base_url = os.getenv("SFTPGO_API_BASE_URL", "http://ftp-server:8080/api/v2")
    api_username = os.getenv("SFTPGO_API_USERNAME", "admin")
    api_password = os.getenv("SFTPGO_API_PASSWORD", "change-me-now")

    stale_after_hours = int(os.getenv("STALE_AFTER_HOURS", "24"))
    stale_after_seconds = stale_after_hours * 3600
    refresh_interval_seconds = int(os.getenv("REFRESH_INTERVAL_SECONDS", "60"))
    timeout_seconds = int(os.getenv("API_TIMEOUT_SECONDS", "10"))

    merge_native_metrics = os.getenv("MERGE_SFTPGO_NATIVE_METRICS", "true").lower() == "true"
    native_metrics_url = os.getenv("SFTPGO_NATIVE_METRICS_URL", "http://ftp-server:10000/metrics")

    admin_session_cookie = os.getenv("EPG_ADMIN_SESSION_COOKIE", "epg_admin_session")
    admin_session_ttl_seconds = int(os.getenv("EPG_ADMIN_SESSION_TTL_SECONDS", "1800"))

    managed_folder_name = os.getenv("EPG_ADMIN_MANAGED_FOLDER_NAME", "epg-bundles")
    managed_folder_path = os.getenv("EPG_ADMIN_MANAGED_FOLDER_PATH", "/srv/epg/EPG")
    managed_group_name = os.getenv("EPG_ADMIN_MANAGED_GROUP_NAME", "epg-customers-ro")
    managed_virtual_path = os.getenv("EPG_ADMIN_MANAGED_VIRTUAL_PATH", "/EPG")
    epg_files_root = os.getenv("EPG_FILES_ROOT", managed_folder_path)
    epg_files_max_entries = int(os.getenv("EPG_FILES_MAX_ENTRIES", "5000"))
    epg_bundle_root = os.getenv("EPG_BUNDLE_ROOT", epg_files_root)
    epg_bundle_expected_count = int(os.getenv("EPG_BUNDLE_EXPECTED_COUNT", "52"))
    epg_bundle_freshness_max_age_hours = int(os.getenv("EPG_BUNDLE_FRESHNESS_MAX_AGE_HOURS", "48"))
    epg_bundle_freshness_max_age_seconds = epg_bundle_freshness_max_age_hours * 3600
    event_state_path = os.getenv(
        "EPG_ADMIN_EVENT_STATE_PATH",
        os.getenv("EPG_ADMIN_DOWNLOAD_STATE_PATH", "/var/lib/epg-admin/sftpgo-events.json"),
    )
    download_event_token = os.getenv("EPG_ADMIN_DOWNLOAD_EVENT_TOKEN", "")

    # Exporter client uses service credentials supplied via environment.
    metrics_client = SFTPGoClient(
        base_url=api_base_url,
        timeout_seconds=timeout_seconds,
        username=api_username,
        password=api_password,
    )
    event_store = SFTPGoEventStore(event_state_path)
    state = ExporterState(
        client=metrics_client,
        refresh_interval_seconds=refresh_interval_seconds,
        event_store=event_store,
    )

    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )
    app.secret_key = os.getenv("EPG_ADMIN_FLASK_SECRET_KEY", "set-epg-admin-flask-secret")

    sessions: Dict[str, AdminSession] = {}
    session_lock = Lock()

    def cleanup_sessions() -> None:
        """Remove expired sessions from in-memory store."""
        now = time.time()
        with session_lock:
            expired = [sid for sid, s in sessions.items() if s.expires_at < now]
            for sid in expired:
                sessions.pop(sid, None)

    def get_admin_session() -> Optional[AdminSession]:
        """Resolve and extend the active session from the auth cookie."""
        cleanup_sessions()
        sid = request.cookies.get(admin_session_cookie, "")
        if not sid:
            return None
        with session_lock:
            session = sessions.get(sid)
            if session is None:
                return None
            session.expires_at = time.time() + admin_session_ttl_seconds
            return session

    def create_session(username: str, password: str) -> str:
        """Create a new in-memory UI session and return the session ID."""
        sid = secrets.token_urlsafe(32)
        with session_lock:
            sessions[sid] = AdminSession(
                session_id=sid,
                username=username,
                password=password,
                expires_at=time.time() + admin_session_ttl_seconds,
            )
        return sid

    def delete_session(sid: str) -> None:
        """Delete a session from the in-memory store."""
        with session_lock:
            sessions.pop(sid, None)

    def require_admin_session() -> Optional[AdminSession]:
        """Return current admin session, or ``None`` if unauthenticated."""
        session = get_admin_session()
        if session is None:
            return None
        return session

    def build_ui_client(session: AdminSession) -> SFTPGoClient:
        """Create a per-request API client bound to the current UI session creds."""
        return SFTPGoClient(
            base_url=api_base_url,
            timeout_seconds=timeout_seconds,
            username=session.username,
            password=session.password,
        )

    def ensure_managed_resources(client: SFTPGoClient) -> None:
        """
        Ensure managed folder/group defaults exist for customer provisioning.

        Created resources are intentionally idempotent:
        - folder mapped to shared EPG path
        - read-only group with virtual mount (default ``/EPG``)
        """
        folder = client.get_folder(managed_folder_name)
        if folder is None:
            client.create_folder(
                {
                    "name": managed_folder_name,
                    "mapped_path": managed_folder_path,
                    "description": "Managed by epg-admin",
                }
            )

        group = client.get_group(managed_group_name)
        if group is None:
            client.create_group(
                {
                    "name": managed_group_name,
                    "description": "Managed read-only EPG access group",
                    "user_settings": {
                        "permissions": {
                            "/": ["list", "download"],
                        }
                    },
                    "virtual_folders": [
                        {
                            "name": managed_folder_name,
                            "virtual_path": managed_virtual_path,
                            "quota_size": 0,
                            "quota_files": 0,
                        }
                    ],
                }
            )

    def api_last_login_ts(last_login_ms: Any) -> float:
        """Return SFTPGo API last_login as Unix seconds, or 0 if missing."""
        if isinstance(last_login_ms, (int, float)) and last_login_ms > 0:
            return float(last_login_ms) / 1000.0
        return 0.0

    def format_last_login(last_login_ts: float) -> tuple[str, bool]:
        """Return human-readable last login string and stale flag."""
        if last_login_ts > 0:
            age = max(0.0, time.time() - last_login_ts)
            return now_utc_iso(last_login_ts), age > stale_after_seconds
        return "Never", False

    def format_last_download(last_download_ts: float) -> tuple[str, bool]:
        """Return human-readable last successful download string and stale flag."""
        if last_download_ts > 0:
            age = max(0.0, time.time() - last_download_ts)
            return now_utc_iso(last_download_ts), age > stale_after_seconds
        return "Never", False

    def build_user_rows(raw_users: List[dict]) -> List[dict]:
        """Transform raw SFTPGo users into table rows for the admin UI."""
        rows = []
        logins = event_store.login_snapshot()
        downloads = event_store.download_snapshot()
        for item in raw_users:
            username = item.get("username")
            if not isinstance(username, str) or not username:
                continue
            status_value = int(item.get("status", 0)) if item.get("status") is not None else 0
            enabled = status_value == 1
            login = logins.get(username)
            last_login_ts = login.last_login_ts if login is not None else api_last_login_ts(item.get("last_login", 0))
            last_login_label, stale = format_last_login(last_login_ts)
            download = downloads.get(username)
            last_download_ts = download.last_download_ts if download is not None else 0.0
            last_download_label, download_stale = format_last_download(last_download_ts)
            rows.append(
                {
                    "username": username,
                    "label": item.get("description", "") or username,
                    "status": "enabled" if enabled else "disabled",
                    "enabled": enabled,
                    "last_login": last_login_label,
                    "last_login_source": "webhook" if login is not None else "sftpgo",
                    "last_download": last_download_label,
                    "last_download_filename": download.filename if download is not None else "",
                    "last_download_path": download.virtual_path if download is not None else "",
                    "download_stale": download_stale if enabled else False,
                    "stale": stale if enabled else False,
                }
            )
        rows.sort(key=lambda r: r["username"])
        return rows

    def format_size(num_bytes: int) -> str:
        """Return a compact human-readable byte size string."""
        if num_bytes < 1024:
            return f"{num_bytes} B"
        units = ["KB", "MB", "GB", "TB", "PB"]
        size = float(num_bytes)
        for unit in units:
            size /= 1024.0
            if size < 1024.0:
                return f"{size:.1f} {unit}"
        return f"{size:.1f} EB"

    def list_epg_files() -> tuple[List[dict], bool]:
        """
        Recursively list files under the configured EPG root path.

        Returns ``(files, truncated)`` where ``truncated`` indicates the
        ``EPG_FILES_MAX_ENTRIES`` limit was reached.
        """
        root = os.path.abspath(epg_files_root)
        if not os.path.isdir(root):
            raise ValueError(f"EPG files root not found: {root}")

        files: List[dict] = []
        truncated = False
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            filenames.sort()
            rel_dir = os.path.relpath(dirpath, root)
            if rel_dir == ".":
                rel_dir = ""

            for filename in filenames:
                full_path = os.path.join(dirpath, filename)
                try:
                    st = os.stat(full_path)
                except OSError:
                    continue
                rel_path = os.path.join(rel_dir, filename).replace(os.sep, "/")
                files.append(
                    {
                        "path": rel_path,
                        "size_bytes": int(st.st_size),
                        "size_label": format_size(int(st.st_size)),
                        "modified": now_utc_iso(float(st.st_mtime)),
                    }
                )
                if len(files) >= epg_files_max_entries:
                    truncated = True
                    break

            if truncated:
                break

        files.sort(key=lambda item: item["path"])
        return files, truncated

    def scan_epg_bundles() -> dict:
        """Return freshness/count details for generated EPG ZIP bundles."""
        root = os.path.abspath(epg_bundle_root)
        result: dict[str, Any] = {
            "root": root,
            "count": 0,
            "latest_ts": 0.0,
            "latest_filename": "",
            "latest_path": "",
            "latest_size": 0,
            "scan_error": "",
        }
        if not os.path.isdir(root):
            result["scan_error"] = "root_not_found"
            return result

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            filenames.sort()
            rel_dir = os.path.relpath(dirpath, root)
            if rel_dir == ".":
                rel_dir = ""

            for filename in filenames:
                if not filename.lower().endswith(".zip"):
                    continue
                full_path = os.path.join(dirpath, filename)
                try:
                    st = os.stat(full_path)
                except OSError:
                    continue

                result["count"] += 1
                modified_ts = float(st.st_mtime)
                if modified_ts >= result["latest_ts"]:
                    result["latest_ts"] = modified_ts
                    result["latest_filename"] = filename
                    result["latest_path"] = os.path.join(rel_dir, filename).replace(os.sep, "/")
                    result["latest_size"] = int(st.st_size)

        return result

    @app.get("/")
    def root() -> Response:
        """Default root route; redirects to user administration view."""
        return redirect(url_for("admin_users"))

    @app.get("/healthz")
    def healthz() -> tuple[dict, int]:
        """Health endpoint used by probes and container healthchecks."""
        state.refresh_if_needed()
        healthy = state.last_success_ts > 0
        status = 200 if healthy else 503
        return {
            "status": "ok" if healthy else "degraded",
            "last_success_timestamp": state.last_success_ts,
            "last_error": state.last_error,
        }, status

    @app.post("/internal/sftpgo/download-event")
    def sftpgo_download_event() -> tuple[dict, int]:
        """Receive SFTPGo successful download hook events."""
        if download_event_token:
            supplied_token = request.headers.get("X-EPG-Event-Token", "") or request.args.get("token", "")
            if not secrets.compare_digest(supplied_token, download_event_token):
                return {"status": "unauthorized"}, 401

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return {"status": "bad_request", "error": "JSON object body required"}, 400

        snap = event_store.record_download(payload)
        if snap is None:
            return {"status": "ignored"}, 202

        return {
            "status": "recorded",
            "username": snap.username,
            "last_download_timestamp": snap.last_download_ts,
            "filename": snap.filename,
        }, 200

    @app.post("/internal/sftpgo/login-event")
    def sftpgo_login_event() -> tuple[dict, int]:
        """Receive SFTPGo successful post-login hook events."""
        if download_event_token:
            supplied_token = request.headers.get("X-EPG-Event-Token", "") or request.args.get("token", "")
            if not secrets.compare_digest(supplied_token, download_event_token):
                return {"status": "unauthorized"}, 401

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return {"status": "bad_request", "error": "JSON object body required"}, 400

        username = payload.get("username")
        if not isinstance(username, str):
            username = ""
        username = username.strip()

        snap = event_store.record_login(
            username=username,
            method=request.args.get("login_method", ""),
            protocol=request.args.get("protocol", ""),
            ip=request.args.get("ip", ""),
            status=int_or_default(request.args.get("status", 0)),
        )
        if snap is None:
            return {"status": "ignored"}, 202

        return {
            "status": "recorded",
            "username": snap.username,
            "last_login_timestamp": snap.last_login_ts,
            "method": snap.method,
            "protocol": snap.protocol,
            "ip": snap.ip,
        }, 200

    @app.get("/metrics")
    def metrics() -> Response:
        """
        Prometheus exposition endpoint.

        Emits custom ``sftpgo_*`` exporter metrics and optionally appends native
        SFTPGo metrics output from ``SFTPGO_NATIVE_METRICS_URL``.
        """
        state.refresh_if_needed()

        registry = CollectorRegistry()
        g_up = Gauge(
            "sftpgo_user_exporter_up",
            "1 if exporter has successfully fetched users at least once",
            registry=registry,
        )
        g_last_success = Gauge(
            "sftpgo_user_exporter_last_success_timestamp",
            "Unix timestamp for last successful fetch from SFTPGo API",
            registry=registry,
        )
        g_errors = Gauge(
            "sftpgo_user_exporter_refresh_errors_total",
            "Total API refresh errors since exporter start",
            registry=registry,
        )

        g_last_login = Gauge(
            "sftpgo_user_last_login_timestamp",
            "Last login time per SFTPGo user as unix timestamp, 0 if never",
            ["username", "customer_label", "status"],
            registry=registry,
        )
        g_age = Gauge(
            "sftpgo_user_seconds_since_last_login",
            "Seconds since last login per SFTPGo user, -1 if never",
            ["username", "customer_label", "status"],
            registry=registry,
        )
        g_stale = Gauge(
            "sftpgo_user_stale",
            "1 when enabled user last login is older than STALE_AFTER_HOURS, else 0",
            ["username", "customer_label", "status"],
            registry=registry,
        )
        g_login_info = Gauge(
            "sftpgo_user_last_login_info",
            "Metadata for the last successful login webhook event per SFTPGo user",
            ["username", "customer_label", "status", "method", "protocol", "ip"],
            registry=registry,
        )
        g_last_download = Gauge(
            "sftpgo_user_last_successful_download_timestamp",
            "Last successful file download time per SFTPGo user as unix timestamp, 0 if never",
            ["username", "customer_label", "status"],
            registry=registry,
        )
        g_download_age = Gauge(
            "sftpgo_user_seconds_since_last_successful_download",
            "Seconds since last successful file download per SFTPGo user, -1 if never",
            ["username", "customer_label", "status"],
            registry=registry,
        )
        g_download_stale = Gauge(
            "sftpgo_user_download_stale",
            "1 when enabled user last successful download is older than STALE_AFTER_HOURS, else 0",
            ["username", "customer_label", "status"],
            registry=registry,
        )
        g_downloads_total = Gauge(
            "sftpgo_user_successful_downloads_total",
            "Successful download events recorded by epg-admin per SFTPGo user",
            ["username", "customer_label", "status"],
            registry=registry,
        )
        g_download_info = Gauge(
            "sftpgo_user_last_successful_download_info",
            "Metadata for the last successful file download per SFTPGo user",
            ["username", "customer_label", "status", "filename", "virtual_path"],
            registry=registry,
        )
        g_bundle_latest_modified = Gauge(
            "epg_bundle_latest_modified_timestamp",
            "Unix timestamp for the newest generated EPG ZIP bundle visible to epg-admin, 0 if none",
            ["root"],
            registry=registry,
        )
        g_bundle_age = Gauge(
            "epg_bundle_seconds_since_latest_modified",
            "Seconds since newest generated EPG ZIP bundle was modified, -1 if none",
            ["root"],
            registry=registry,
        )
        g_bundle_count = Gauge(
            "epg_bundle_file_count",
            "Number of generated EPG ZIP bundles currently visible to epg-admin",
            ["root"],
            registry=registry,
        )
        g_bundle_expected_count = Gauge(
            "epg_bundle_expected_file_count",
            "Expected number of generated EPG ZIP bundles",
            ["root"],
            registry=registry,
        )
        g_bundle_missing_count = Gauge(
            "epg_bundle_missing_expected_file_count",
            "Expected EPG ZIP bundle count minus visible count, floored at 0",
            ["root"],
            registry=registry,
        )
        g_bundle_generation_stale = Gauge(
            "epg_bundle_generation_stale",
            "1 when generated EPG bundles are missing or newest bundle is older than EPG_BUNDLE_FRESHNESS_MAX_AGE_HOURS",
            ["root"],
            registry=registry,
        )
        g_bundle_latest_info = Gauge(
            "epg_bundle_latest_info",
            "Metadata for the newest generated EPG ZIP bundle visible to epg-admin",
            ["root", "filename", "relative_path"],
            registry=registry,
        )
        g_bundle_scan_error = Gauge(
            "epg_bundle_scan_error",
            "1 when epg-admin cannot scan the configured EPG bundle root",
            ["root", "error"],
            registry=registry,
        )

        g_up.set(1 if state.last_success_ts > 0 else 0)
        g_last_success.set(state.last_success_ts)
        g_errors.set(state.error_count)

        now = time.time()
        bundle_scan = scan_epg_bundles()
        bundle_root = str(bundle_scan["root"])
        bundle_count = int(bundle_scan["count"])
        bundle_latest_ts = float(bundle_scan["latest_ts"])
        bundle_age_seconds = -1.0 if bundle_latest_ts <= 0 else max(0.0, now - bundle_latest_ts)
        bundle_missing_count = max(0, epg_bundle_expected_count - bundle_count)
        bundle_scan_error = str(bundle_scan["scan_error"])
        bundle_is_stale = (
            bool(bundle_scan_error)
            or bundle_latest_ts <= 0
            or bundle_missing_count > 0
            or bundle_age_seconds > epg_bundle_freshness_max_age_seconds
        )

        g_bundle_latest_modified.labels(root=bundle_root).set(bundle_latest_ts)
        g_bundle_age.labels(root=bundle_root).set(bundle_age_seconds)
        g_bundle_count.labels(root=bundle_root).set(bundle_count)
        g_bundle_expected_count.labels(root=bundle_root).set(epg_bundle_expected_count)
        g_bundle_missing_count.labels(root=bundle_root).set(bundle_missing_count)
        g_bundle_generation_stale.labels(root=bundle_root).set(1 if bundle_is_stale else 0)
        g_bundle_scan_error.labels(root=bundle_root, error=bundle_scan_error or "none").set(1 if bundle_scan_error else 0)
        if bundle_latest_ts > 0:
            g_bundle_latest_info.labels(
                root=bundle_root,
                filename=str(bundle_scan["latest_filename"]),
                relative_path=str(bundle_scan["latest_path"]),
            ).set(1)

        logins = event_store.login_snapshot()
        downloads = event_store.download_snapshot()
        for username in sorted(state.users.keys()):
            snap = state.users[username]
            customer_label = username
            login = logins.get(username)
            last_login_ts = login.last_login_ts if login is not None else snap.last_login_ts
            age_seconds = -1.0 if last_login_ts <= 0 else max(0.0, now - last_login_ts)
            download = downloads.get(username)
            last_download_ts = download.last_download_ts if download is not None else 0.0
            download_age_seconds = -1.0 if last_download_ts <= 0 else max(0.0, now - last_download_ts)

            if snap.status != "enabled":
                stale = 0
            elif age_seconds < 0:
                stale = 0
            else:
                stale = 1 if age_seconds > stale_after_seconds else 0

            if snap.status != "enabled":
                download_stale = 0
            elif download_age_seconds < 0:
                download_stale = 0
            else:
                download_stale = 1 if download_age_seconds > stale_after_seconds else 0

            labels = {
                "username": username,
                "customer_label": customer_label,
                "status": snap.status,
            }
            g_last_login.labels(**labels).set(last_login_ts)
            g_age.labels(**labels).set(age_seconds)
            g_stale.labels(**labels).set(stale)
            if login is not None:
                g_login_info.labels(
                    **labels,
                    method=login.method,
                    protocol=login.protocol,
                    ip=login.ip,
                ).set(1)
            g_last_download.labels(**labels).set(last_download_ts)
            g_download_age.labels(**labels).set(download_age_seconds)
            g_download_stale.labels(**labels).set(download_stale)
            g_downloads_total.labels(**labels).set(download.successful_downloads if download is not None else 0)
            if download is not None:
                g_download_info.labels(
                    **labels,
                    filename=download.filename,
                    virtual_path=download.virtual_path,
                ).set(1)

        exporter_output = generate_latest(registry).decode("utf-8")
        if not merge_native_metrics:
            return Response(exporter_output, mimetype="text/plain; version=0.0.4; charset=utf-8")

        merged_parts = [exporter_output.rstrip("\n")]
        try:
            req = Request(url=native_metrics_url, method="GET")
            with urlopen(req, timeout=timeout_seconds) as resp:
                native_output = resp.read().decode("utf-8", errors="replace").rstrip("\n")
                if native_output:
                    merged_parts.append(native_output)
        except (HTTPError, URLError, OSError) as exc:
            merged_parts.append(f"# sftpgo_native_metrics_scrape_error {type(exc).__name__}: {exc}")

        merged_output = "\n\n".join(merged_parts) + "\n"
        return Response(merged_output, mimetype="text/plain; version=0.0.4; charset=utf-8")

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login() -> Response:
        """Render login form and establish a UI session on successful auth."""
        error = ""
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            if not username or not password:
                error = "Username and password are required"
            else:
                try:
                    client = SFTPGoClient(api_base_url, timeout_seconds, username, password)
                    client._ensure_token()
                    sid = create_session(username, password)
                    response = make_response(redirect(url_for("admin_users")))
                    response.set_cookie(
                        admin_session_cookie,
                        sid,
                        httponly=True,
                        samesite="Lax",
                        max_age=admin_session_ttl_seconds,
                    )
                    return response
                except (HTTPError, URLError, ValueError, OSError):
                    error = "Authentication failed"

        return Response(render_template("admin_login.html", error=error), mimetype="text/html")

    @app.post("/admin/logout")
    def admin_logout() -> Response:
        """Terminate current session and redirect to login."""
        sid = request.cookies.get(admin_session_cookie, "")
        if sid:
            delete_session(sid)
        response = make_response(redirect(url_for("admin_login")))
        response.delete_cookie(admin_session_cookie)
        return response

    @app.get("/admin/users")
    def admin_users() -> Response:
        """Render customer user table with login freshness/staleness status."""
        session = require_admin_session()
        if session is None:
            return redirect(url_for("admin_login"))

        error = ""
        rows: List[dict] = []
        flashes = get_flashed_messages(with_categories=True)
        try:
            client = build_ui_client(session)
            rows = build_user_rows(client.fetch_users())
        except (HTTPError, URLError, ValueError, OSError) as exc:
            error = f"Failed to load users: {exc}"

        html = render_template(
            "admin_users.html",
            admin_username=session.username,
            users=rows,
            flashes=flashes,
            error=error,
            refreshed_at=now_utc_iso(),
        )
        return Response(html, mimetype="text/html")

    @app.get("/admin/files")
    def admin_files() -> Response:
        """Render an inventory of files available under the shared EPG root."""
        session = require_admin_session()
        if session is None:
            return redirect(url_for("admin_login"))

        error = ""
        files: List[dict] = []
        truncated = False
        try:
            files, truncated = list_epg_files()
        except (ValueError, OSError) as exc:
            error = f"Failed to read files: {exc}"

        html = render_template(
            "admin_files.html",
            admin_username=session.username,
            files=files,
            truncated=truncated,
            files_root=os.path.abspath(epg_files_root),
            refreshed_at=now_utc_iso(),
            error=error,
        )
        return Response(html, mimetype="text/html")

    @app.route("/admin/users/create", methods=["GET", "POST"])
    def admin_create_user() -> Response:
        """Create a managed customer user with read-only EPG access defaults."""
        session = require_admin_session()
        if session is None:
            return redirect(url_for("admin_login"))

        error = ""

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            label = request.form.get("label", "").strip()
            password = request.form.get("password", "")

            if not username:
                error = "Username is required"
            elif not password:
                error = "Password is required"

            if not error:
                try:
                    client = build_ui_client(session)
                    ensure_managed_resources(client)

                    payload = {
                        "status": 1,
                        "username": username,
                        "password": password,
                        "description": label,
                        "home_dir": managed_folder_path,
                        "permissions": {
                            "/": ["list", "download"],
                        },
                        "groups": [
                            {
                                "name": managed_group_name,
                                "type": 1,
                            }
                        ],
                    }
                    client.create_user(payload)
                    flash(f"Created user {username}", "success")
                    return redirect(url_for("admin_users"))
                except HTTPError as exc:
                    error = f"Failed to create user: HTTP {exc.code}"
                except (URLError, ValueError, OSError) as exc:
                    error = f"Failed to create user: {exc}"

        html = render_template("admin_create_user.html", error=error)
        return Response(html, mimetype="text/html")

    @app.post("/admin/users/<username>/disable")
    def admin_disable_user(username: str) -> Response:
        """Disable the specified SFTPGo user account."""
        session = require_admin_session()
        if session is None:
            return redirect(url_for("admin_login"))

        try:
            client = build_ui_client(session)
            user = client.get_user(username)
            if user is None:
                flash(f"User {username} not found", "warning")
                return redirect(url_for("admin_users"))
            payload = sanitize_user_for_update(user)
            payload["status"] = 0
            client.update_user(username, payload)
            flash(f"Disabled user {username}", "success")
            return redirect(url_for("admin_users"))
        except HTTPError as exc:
            flash(f"Failed to disable {username}: HTTP {exc.code}", "danger")
            return redirect(url_for("admin_users"))
        except (URLError, ValueError, OSError) as exc:
            flash(f"Failed to disable {username}: {exc}", "danger")
            return redirect(url_for("admin_users"))

    @app.post("/admin/users/<username>/status")
    def admin_set_user_status(username: str) -> Response:
        """Set account status (enabled/disabled) for the specified SFTPGo user."""
        session = require_admin_session()
        if session is None:
            return redirect(url_for("admin_login"))

        enabled_value = request.form.get("enabled", "").strip().lower()
        if enabled_value in {"1", "true", "enabled"}:
            target_status = 1
            action_label = "enabled"
        elif enabled_value in {"0", "false", "disabled"}:
            target_status = 0
            action_label = "disabled"
        else:
            flash(f"Invalid status request for {username}", "warning")
            return redirect(url_for("admin_users"))

        try:
            client = build_ui_client(session)
            user = client.get_user(username)
            if user is None:
                flash(f"User {username} not found", "warning")
                return redirect(url_for("admin_users"))
            payload = sanitize_user_for_update(user)
            payload["status"] = target_status
            client.update_user(username, payload)
            flash(f"{action_label.capitalize()} user {username}", "success")
            return redirect(url_for("admin_users"))
        except HTTPError as exc:
            flash(f"Failed to update {username}: HTTP {exc.code}", "danger")
            return redirect(url_for("admin_users"))
        except (URLError, ValueError, OSError) as exc:
            flash(f"Failed to update {username}: {exc}", "danger")
            return redirect(url_for("admin_users"))

    @app.post("/admin/users/<username>/delete")
    def admin_delete_user(username: str) -> Response:
        """Delete the specified SFTPGo user account."""
        session = require_admin_session()
        if session is None:
            return redirect(url_for("admin_login"))

        try:
            client = build_ui_client(session)
            user = client.get_user(username)
            if user is None:
                flash(f"User {username} not found", "warning")
                return redirect(url_for("admin_users"))
            client.delete_user(username)
            flash(f"Deleted user {username}", "success")
            return redirect(url_for("admin_users"))
        except HTTPError as exc:
            flash(f"Failed to delete {username}: HTTP {exc.code}", "danger")
            return redirect(url_for("admin_users"))
        except (URLError, ValueError, OSError) as exc:
            flash(f"Failed to delete {username}: {exc}", "danger")
            return redirect(url_for("admin_users"))

    @app.route("/admin/users/<username>/change-password", methods=["GET", "POST"])
    @app.route("/admin/users/<username>/edit", methods=["GET", "POST"])
    @app.route("/admin/users/<username>/reset-password", methods=["GET", "POST"])
    def admin_change_password(username: str) -> Response:
        """Change the specified SFTPGo user's password."""
        session = require_admin_session()
        if session is None:
            return redirect(url_for("admin_login"))

        error = ""
        try:
            client = build_ui_client(session)
            user = client.get_user(username)
            if user is None:
                flash(f"User {username} not found", "warning")
                return redirect(url_for("admin_users"))
            if request.method == "POST":
                new_password = request.form.get("new_password", "")
                attempted_password_reset = bool(new_password)
                if not attempted_password_reset:
                    error = "Provide a new password"
                else:
                    payload = sanitize_user_for_update(user)
                    payload["password"] = new_password
                    client.update_user(username, payload)
                    flash(f"Password reset for {username}", "success")
                    return redirect(url_for("admin_users"))
        except HTTPError as exc:
            if request.method == "POST":
                flash(f"Failed update for {username}: HTTP {exc.code}", "danger")
                return redirect(url_for("admin_users"))
            else:
                flash(f"Failed to load {username}: HTTP {exc.code}", "danger")
                return redirect(url_for("admin_users"))
        except (URLError, ValueError, OSError) as exc:
            if request.method == "POST":
                flash(f"Failed update for {username}: {exc}", "danger")
                return redirect(url_for("admin_users"))
            else:
                flash(f"Failed to load {username}: {exc}", "danger")
                return redirect(url_for("admin_users"))

        html = render_template(
            "admin_reset_password.html",
            username=username,
            error=error,
        )
        return Response(html, mimetype="text/html")

    @app.route("/admin/users/<username>/ip-whitelist", methods=["GET", "POST"])
    def admin_user_ip_whitelist(username: str) -> Response:
        """View or update per-user allowed IP/CIDR whitelist."""
        session = require_admin_session()
        if session is None:
            return redirect(url_for("admin_login"))

        error = ""
        ip_whitelist_text = ""

        try:
            client = build_ui_client(session)
            user = client.get_user(username)
            if user is None:
                flash(f"User {username} not found", "warning")
                return redirect(url_for("admin_users"))
        except HTTPError as exc:
            flash(f"Failed to load {username}: HTTP {exc.code}", "danger")
            return redirect(url_for("admin_users"))
        except (URLError, ValueError, OSError) as exc:
            flash(f"Failed to load {username}: {exc}", "danger")
            return redirect(url_for("admin_users"))

        if request.method == "POST":
            raw_input = request.form.get("allowed_ips", "")
            entries = [line.strip() for line in raw_input.replace(",", "\n").splitlines()]
            allowed_ips = [entry for entry in entries if entry]

            invalid_entries: List[str] = []
            for entry in allowed_ips:
                try:
                    ipaddress.ip_network(entry, strict=False)
                except ValueError:
                    invalid_entries.append(entry)

            if invalid_entries:
                error = (
                    "Invalid IP/CIDR entry: "
                    + ", ".join(invalid_entries[:5])
                    + ("..." if len(invalid_entries) > 5 else "")
                )
                ip_whitelist_text = raw_input
            else:
                try:
                    payload = sanitize_user_for_update(user)
                    filters = payload.get("filters")
                    if not isinstance(filters, dict):
                        filters = {}
                    if allowed_ips:
                        filters["allowed_ip"] = allowed_ips
                    else:
                        filters.pop("allowed_ip", None)
                    payload["filters"] = filters
                    client.update_user(username, payload)
                    if allowed_ips:
                        notice = f"Updated IP whitelist for {username} ({len(allowed_ips)} entries)"
                    else:
                        notice = f"Cleared IP whitelist for {username}"
                    flash(notice, "success")
                    return redirect(url_for("admin_users"))
                except HTTPError as exc:
                    error = f"Failed to update whitelist: HTTP {exc.code}"
                    ip_whitelist_text = raw_input
                except (URLError, ValueError, OSError) as exc:
                    error = f"Failed to update whitelist: {exc}"
                    ip_whitelist_text = raw_input
        else:
            filters = user.get("filters")
            allowed_ip_values: List[str] = []
            if isinstance(filters, dict):
                raw_allowed = filters.get("allowed_ip")
                if isinstance(raw_allowed, list):
                    allowed_ip_values = [str(item).strip() for item in raw_allowed if str(item).strip()]
            ip_whitelist_text = "\n".join(allowed_ip_values)

        html = render_template(
            "admin_user_ip_whitelist.html",
            username=username,
            error=error,
            ip_whitelist_text=ip_whitelist_text,
        )
        return Response(html, mimetype="text/html")

    return app


app = create_app()


if __name__ == "__main__":
    """Run Waitress WSGI server for local/container execution."""
    port = int(os.getenv("PORT", "8081"))
    threads = int(os.getenv("WAITRESS_THREADS", "2"))
    connection_limit = int(os.getenv("WAITRESS_CONNECTION_LIMIT", "50"))
    serve(
        app,
        host="0.0.0.0",
        port=port,
        threads=threads,
        connection_limit=connection_limit,
    )

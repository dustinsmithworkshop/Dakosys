#!/usr/bin/env python3
"""
Improved Trakt.tv Authentication Module for DAKOSYS
Handles authentication, token refresh, and persistent sessions with simplified flows
"""

import os
import json
import time
import yaml
import requests
import logging
from rich.console import Console

# Initialize console and logger
console = Console()
logger = logging.getLogger("trakt_auth")

# Constants
DEFAULT_CONFIG_PATH = "config/config.yaml"
DEFAULT_DATA_DIR = "data"

# Module-level rate limit state — shared across all make_trakt_request calls
_rate_limited_until: float = 0  # epoch seconds

def get_config_path():
    """Get the appropriate config path based on environment."""
    if os.environ.get('RUNNING_IN_DOCKER') == 'true':
        return "/app/config/config.yaml"
    return DEFAULT_CONFIG_PATH

def get_data_dir():
    """Get the appropriate data directory based on environment."""
    if os.environ.get('RUNNING_IN_DOCKER') == 'true':
        return "/app/data"
    return DEFAULT_DATA_DIR

def load_config():
    """Load configuration from YAML file."""
    config_path = get_config_path()
    
    try:
        if not os.path.exists(config_path):
            logger.error(f"Configuration file not found at {config_path}")
            console.print(f"[bold red]Configuration file not found at {config_path}[/bold red]")
            return None
            
        with open(config_path, 'r') as file:
            config = yaml.safe_load(file)
            
        return config
    except Exception as e:
        logger.error(f"Error loading configuration: {str(e)}")
        console.print(f"[bold red]Error loading configuration: {str(e)}[/bold red]")
        return None

def get_stored_trakt_tokens():
    """Retrieve stored Trakt access token and refresh token."""
    token_file = os.path.join(get_data_dir(), 'trakt_token.json')
    try:
        if os.path.exists(token_file):
            with open(token_file, 'r') as file:
                data = json.load(file)
                return data.get('access_token'), data.get('refresh_token'), data.get('created_at', 0), data.get('expires_in', 0)
    except Exception as e:
        logger.warning(f"Error reading token file: {str(e)}")
        console.print(f"[yellow]Error reading token file: {str(e)}[/yellow]")
    return None, None, 0, 0

def store_trakt_tokens(access_token, refresh_token, created_at, expires_in):
    """Store Trakt access and refresh tokens."""
    data_dir = get_data_dir()
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        
    token_file = os.path.join(data_dir, 'trakt_token.json')
    try:
        with open(token_file, 'w') as file:
            json.dump({
                'access_token': access_token,
                'refresh_token': refresh_token,
                'created_at': created_at,
                'expires_in': expires_in
            }, file)
        return True
    except Exception as e:
        logger.error(f"Error storing tokens: {str(e)}")
        console.print(f"[bold red]Error storing tokens: {str(e)}[/bold red]")
        return False

def get_device_code(config=None):
    """Get a device code using Trakt's device authentication flow."""
    if config is None:
        config = load_config()
        if not config:
            return None, None
            
    try:
        trakt_api_url = 'https://api.trakt.tv'
        headers = {
            'Content-Type': 'application/json',
            'trakt-api-key': config['trakt']['client_id'],
            'trakt-api-version': '2',
        }
        
        # Request device code
        device_code_url = f'{trakt_api_url}/oauth/device/code'
        payload = {
            'client_id': config['trakt']['client_id'],
        }
        
        response = requests.post(device_code_url, json=payload, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            device_code = data.get('device_code')
            user_code = data.get('user_code')
            verification_url = data.get('verification_url')
            expires_in = data.get('expires_in', 600)  # Usually 10 minutes
            interval = data.get('interval', 5)  # Usually 5 seconds
            
            return {
                'device_code': device_code,
                'user_code': user_code,
                'verification_url': verification_url,
                'expires_in': expires_in,
                'interval': interval
            }, None
        else:
            logger.error(f"Failed to get device code. Status Code: {response.status_code}, Response: {response.text}")
            return None, f"Failed to get device code. Status Code: {response.status_code}"
    except Exception as e:
        logger.error(f"Error getting device code: {str(e)}")
        return None, f"Error getting device code: {str(e)}"

def poll_for_token(device_code, interval, expires_in, config=None):
    """Poll for access token using device code."""
    if config is None:
        config = load_config()
        if not config:
            return None, None
            
    try:
        trakt_api_url = 'https://api.trakt.tv'
        headers = {
            'Content-Type': 'application/json',
            'trakt-api-key': config['trakt']['client_id'],
            'trakt-api-version': '2',
        }
        
        # Poll for token
        token_url = f'{trakt_api_url}/oauth/device/token'
        payload = {
            'code': device_code,
            'client_id': config['trakt']['client_id'],
            'client_secret': config['trakt']['client_secret'],
        }
        
        start_time = time.time()
        console.print("[yellow]Waiting for authorization...[/yellow]")
        
        while time.time() - start_time < expires_in:
            response = requests.post(token_url, json=payload, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                access_token = data.get('access_token')
                refresh_token = data.get('refresh_token')
                token_expires_in = data.get('expires_in', 7776000)  # 90 days in seconds
                created_at = int(time.time())
                
                store_trakt_tokens(access_token, refresh_token, created_at, token_expires_in)
                return access_token, None
            elif response.status_code == 400:
                # User hasn't authorized yet, wait and try again
                time.sleep(interval)
            elif response.status_code == 404:
                # Invalid device code
                return None, "Invalid device code"
            elif response.status_code == 409:
                # Already used
                return None, "Device code already used"
            elif response.status_code == 410:
                # Expired
                return None, "Device code expired"
            elif response.status_code == 418:
                # Denied by user
                return None, "Authorization denied by user"
            elif response.status_code == 429:
                # Rate limited
                retry_after = int(response.headers.get('Retry-After', interval))
                time.sleep(retry_after)
            else:
                return None, f"Error polling for token. Status Code: {response.status_code}"
        
        return None, "Timeout waiting for authorization"
    except Exception as e:
        logger.error(f"Error polling for token: {str(e)}")
        return None, f"Error polling for token: {str(e)}"

def direct_token_auth(config=None):
    """Attempt to get token using client credentials (useful for single-user access)."""
    if config is None:
        config = load_config()
        if not config:
            return None, None
            
    try:
        trakt_api_url = 'https://api.trakt.tv'
        headers = {
            'Content-Type': 'application/json',
            'trakt-api-key': config['trakt']['client_id'],
            'trakt-api-version': '2',
        }
        
        # Try client credentials flow
        token_url = f'{trakt_api_url}/oauth/token'
        payload = {
            'client_id': config['trakt']['client_id'],
            'client_secret': config['trakt']['client_secret'],
            'grant_type': 'client_credentials',
        }
        
        response = requests.post(token_url, json=payload, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            access_token = data.get('access_token')
            created_at = int(time.time())
            expires_in = data.get('expires_in', 7776000)  # Default to 90 days
            
            # This flow doesn't provide a refresh token
            store_trakt_tokens(access_token, None, created_at, expires_in)
            return access_token, None
        else:
            logger.error(f"Failed to get token with client credentials. Status Code: {response.status_code}, Response: {response.text}")
            return None, f"Failed to get token with client credentials. Status Code: {response.status_code}"
    except Exception as e:
        logger.error(f"Error with client credentials auth: {str(e)}")
        return None, f"Error with client credentials auth: {str(e)}"

def refresh_trakt_token(refresh_token, config=None):
    """Refresh Trakt access token using refresh token."""
    try:
        if config is None:
            config = load_config()
            if not config:
                return None
                
        trakt_auth_url = 'https://api.trakt.tv/oauth/token'

        refresh_payload = {
            'refresh_token': refresh_token,
            'client_id': config['trakt']['client_id'],
            'client_secret': config['trakt']['client_secret'],
            'redirect_uri': config['trakt']['redirect_uri'],
            'grant_type': 'refresh_token',
        }

        response = requests.post(trakt_auth_url, json=refresh_payload)

        if response.status_code == 200:
            token_data = response.json()
            access_token = token_data.get('access_token')
            new_refresh_token = token_data.get('refresh_token')
            expires_in = token_data.get('expires_in', 7776000)  # Default 90 days in seconds
            created_at = int(time.time())
            
            store_trakt_tokens(access_token, new_refresh_token, created_at, expires_in)
            logger.info("Successfully refreshed Trakt access token")
            return access_token
        else:
            logger.error(f"Failed to refresh Trakt access token. Status Code: {response.status_code}, Response: {response.text}")
            console.print(f"[bold red]Failed to refresh Trakt access token. Status Code: {response.status_code}[/bold red]")
            console.print(f"[yellow]Response: {response.text}[/yellow]")
            return None
    except Exception as e:
        logger.error(f"Error during token refresh: {str(e)}")
        console.print(f"[bold red]Error during token refresh: {str(e)}[/bold red]")
        return None

def perform_device_auth(config=None, quiet=False):
    """Perform device code authentication flow."""
    if not quiet:
        console.print("[bold]Trakt.tv Authentication Required[/bold]")
        
    # Start device auth flow
    device_info, error = get_device_code(config)
    if error:
        if not quiet:
            console.print(f"[bold red]Error: {error}[/bold red]")
        return None
    
    if not quiet:
        console.print(f"\n[bold]To authorize DAKOSYS, please:[/bold]")
        console.print(f"1. Go to: [bold blue]{device_info['verification_url']}[/bold blue]")
        console.print(f"2. Enter code: [bold green]{device_info['user_code']}[/bold green]")
        console.print(f"\nThe code expires in {device_info['expires_in'] // 60} minutes.")
    
    # Poll for token
    access_token, error = poll_for_token(
        device_info['device_code'], 
        device_info['interval'], 
        device_info['expires_in'],
        config
    )
    
    if error:
        if not quiet:
            console.print(f"[bold red]Error: {error}[/bold red]")
        return None
    
    if not quiet and access_token:
        console.print("[bold green]Successfully authenticated with Trakt.tv![/bold green]")
    
    return access_token

def ensure_trakt_auth(quiet=False):
    """Ensure we have a valid Trakt authorization.
    
    Args:
        quiet: If True, suppresses console output
    
    Returns:
        Access token string or None
    """
    config = load_config()
    if not config:
        return None
        
    access_token = get_access_token(config=config, quiet=quiet)
    if not access_token and not quiet:
        console.print("[bold red]Failed to authenticate with Trakt.tv.[/bold red]")
    
    return access_token

def get_trakt_headers(access_token=None):
    """Get headers for Trakt API requests."""
    if not access_token:
        access_token = ensure_trakt_auth(quiet=True)
        if not access_token:
            return None
    
    config = load_config()
    if not config:
        return None
        
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {access_token}',
        'trakt-api-key': config['trakt']['client_id'],
        'trakt-api-version': '2',
    }

def get_access_token(config=None, quiet=False):
    """Get a valid access token using the most appropriate method."""
    if config is None:
        config = load_config()
        if not config:
            return None
    
    # First check if we have stored tokens
    access_token, refresh_token, created_at, expires_in = get_stored_trakt_tokens()
    
    # Check if access token exists and is still valid (with 1 hour buffer)
    current_time = int(time.time())
    if access_token and refresh_token and created_at + expires_in - 3600 > current_time:
        logger.debug("Using existing valid access token with refresh token")
        return access_token
    elif access_token and not refresh_token and created_at + expires_in - 3600 > current_time:
        # We have a client credentials token - but we need a user token
        logger.warning("Found client credentials token without refresh token - need user token")
        if not quiet:
            console.print("[yellow]Current token doesn't have user access. Need to authenticate as user.[/yellow]")
        # Fall through to device auth
    elif refresh_token:
        if not quiet:
            console.print("[yellow]Access token expired, attempting to refresh...[/yellow]")
        new_access_token = refresh_trakt_token(refresh_token, config)
        if new_access_token:
            if not quiet:
                console.print("[green]Successfully refreshed Trakt access token.[/green]")
            return new_access_token
        else:
            if not quiet:
                console.print("[yellow]Token refresh failed, will need to re-authorize.[/yellow]")
    
    # Skip client credentials - we need user context
    # Use device code flow directly (user authentication)
    return perform_device_auth(config, quiet)

def ensure_auth_during_setup(config):
    """Initialize authentication during setup."""
    # Create data directory if it doesn't exist
    data_dir = get_data_dir()
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    
    console.print("\n[bold]Authenticating with Trakt.tv...[/bold]")
    console.print("[yellow]This will authorize DAKOSYS to access your Trakt.tv account.[/yellow]")
    
    # Skip client credentials and use device code flow directly
    console.print("[blue]Setting up user authentication via device code...[/blue]")
    access_token = perform_device_auth(config)
    
    if access_token:
        # Verify the user matches the config
        trakt_api_url = 'https://api.trakt.tv'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}',
            'trakt-api-key': config['trakt']['client_id'],
            'trakt-api-version': '2',
        }
        
        # Get authenticated user
        me_url = f'{trakt_api_url}/users/me'
        response = requests.get(me_url, headers=headers)
        
        if response.status_code == 200:
            user_data = response.json()
            authenticated_username = user_data.get('username')
            
            if authenticated_username != config['trakt']['username']:
                console.print(f"[yellow]Warning: Authenticated as '{authenticated_username}' but config has '{config['trakt']['username']}'[/yellow]")
                console.print("[yellow]Updating username in config to match authenticated user[/yellow]")
                
                # Update config
                config['trakt']['username'] = authenticated_username
                
                # Save config
                if os.environ.get('RUNNING_IN_DOCKER') == 'true':
                    config_path = "/app/config/config.yaml"
                else:
                    config_path = get_config_path()
                    
                with open(config_path, 'w') as file:
                    yaml.dump(config, file)
                
            console.print(f"[green]Successfully authenticated as {authenticated_username}[/green]")
        else:
            console.print(f"[yellow]Could not verify username (status {response.status_code})[/yellow]")
        
        return True
    else:
        console.print("[bold yellow]Authentication can be completed later when running commands.[/bold yellow]")
        return False

def get_rate_limit_remaining() -> float:
    """Return seconds until the Trakt rate limit expires, or 0 if not limited."""
    return max(0.0, _rate_limited_until - time.time())


def make_trakt_request(endpoint, method="GET", data=None, params=None):
    """Make an authenticated request to the Trakt API."""
    global _rate_limited_until

    # Bail early if still rate-limited — don't hammer the blocked endpoint
    remaining = _rate_limited_until - time.time()
    if remaining > 0:
        logger.warning(f"Trakt rate limit active, skipping request to {endpoint} (retry in {remaining:.0f}s)")
        return None

    headers = get_trakt_headers()
    if not headers:
        return None

    trakt_api_url = 'https://api.trakt.tv'
    url = f"{trakt_api_url}/{endpoint.lstrip('/')}"

    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=headers, params=params)
        elif method.upper() == "POST":
            response = requests.post(url, headers=headers, json=data, params=params)
        elif method.upper() == "PUT":
            response = requests.put(url, headers=headers, json=data, params=params)
        elif method.upper() == "DELETE":
            response = requests.delete(url, headers=headers, params=params)
        else:
            logger.error(f"Unsupported HTTP method: {method}")
            return None

        if response.status_code in (200, 201, 204):
            _rate_limited_until = 0  # clear any lingering rate limit on success
            if response.status_code == 204 or not response.text:
                return True
            return response.json()
        elif response.status_code == 429:
            retry_after = 60  # conservative default
            try:
                retry_after = int(response.headers.get('Retry-After', retry_after))
            except (ValueError, TypeError):
                pass
            _rate_limited_until = time.time() + retry_after
            logger.warning(f"Trakt rate limit hit (429) for {endpoint} — blocking further requests for {retry_after}s")
            return None
        elif response.status_code == 404 and 'users/' in endpoint:
            # Specific error for user not found
            username = endpoint.split('users/')[1].split('/')[0]
            logger.error(f"User '{username}' not found on Trakt or token lacks permission")
            return None
        else:
            logger.error(f"Trakt API error: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        logger.error(f"Error making Trakt API request: {str(e)}")
        return None

def get_trakt_account_capabilities():
    """
    Return capability information reported by Trakt for the authenticated user.

    The Trakt /users/settings endpoint is authoritative for account limits and
    permissions. Do not infer capabilities from VIP status alone.
    """
    settings = make_trakt_request("users/settings")

    if not isinstance(settings, dict):
        logger.error(
            "Could not retrieve Trakt account capabilities"
        )
        return None

    raw_user = settings.get("user", {}) or {}
    raw_limits = settings.get("limits", {}) or {}
    raw_permissions = settings.get("permissions", {}) or {}

    if not isinstance(raw_user, dict):
        raw_user = {}

    if not isinstance(raw_limits, dict):
        raw_limits = {}

    if not isinstance(raw_permissions, dict):
        raw_permissions = {}

    # Keep the account summary intentionally small. We only need identity and
    # plan-related fields here; do not expose unrelated user settings.
    user = {
        key: raw_user[key]
        for key in ("username", "vip", "vip_ep")
        if key in raw_user
    }

    return {
        "user": user,
        "limits": raw_limits,
        "permissions": raw_permissions,
    }


def _optional_nonnegative_int(value):
    """Return a non-negative integer or None for an unusable API value."""
    if isinstance(value, bool):
        return None

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None

    if parsed < 0:
        return None

    return parsed


def get_trakt_list_capabilities(capabilities=None):
    """
    Normalize the personal-list limits reported by Trakt.

    Only fields actually returned by /users/settings are represented here.
    Missing limits remain unknown rather than being filled with assumed
    Free/VIP defaults.
    """
    if capabilities is None:
        capabilities = get_trakt_account_capabilities()

    if not isinstance(capabilities, dict):
        return None

    user = capabilities.get("user", {}) or {}
    limits = capabilities.get("limits", {}) or {}
    permissions = capabilities.get("permissions", {}) or {}

    if not isinstance(user, dict):
        user = {}

    if not isinstance(limits, dict):
        limits = {}

    if not isinstance(permissions, dict):
        permissions = {}

    list_limits = limits.get("list", {}) or {}
    if not isinstance(list_limits, dict):
        list_limits = {}

    vip = user.get("vip")
    if not isinstance(vip, bool):
        vip = None

    vip_ep = user.get("vip_ep")
    if not isinstance(vip_ep, bool):
        vip_ep = None

    max_lists = _optional_nonnegative_int(
        list_limits.get("count")
    )
    max_items_per_list = _optional_nonnegative_int(
        list_limits.get("item_count")
    )

    return {
        "username": user.get("username"),
        "vip": vip,
        "vip_ep": vip_ep,
        "max_lists": max_lists,
        "max_items_per_list": max_items_per_list,
        "limits_known": (
            max_lists is not None
            and max_items_per_list is not None
        ),
        "permissions": permissions,
    }


def _get_all_trakt_pages(endpoint, *, page_size=100):
    """
    Retrieve all pages from a Trakt endpoint that returns a JSON list.

    Stops when a page contains fewer than page_size items. Any request or
    response failure returns None so callers can fail closed.
    """
    page = 1
    items = []

    while True:
        batch = make_trakt_request(
            endpoint,
            params={
                "page": page,
                "limit": page_size,
            },
        )

        if batch is None:
            return None

        if not isinstance(batch, list):
            logger.error(
                "Unexpected Trakt response type for %s: %s",
                endpoint,
                type(batch).__name__,
            )
            return None

        items.extend(batch)

        if len(batch) < page_size:
            break

        page += 1

    return items


def get_trakt_list_usage(
    *,
    tracked_list_name="Next Airing",
):
    """
    Return current personal-list usage plus capacity for one tracked list.

    This function is read-only. It never creates, updates, or deletes lists.
    Missing account limits or failed API requests remain unknown rather than
    being replaced with assumed Free/VIP defaults.
    """
    capabilities = get_trakt_list_capabilities()

    if capabilities is None:
        return None

    lists = _get_all_trakt_pages("users/me/lists")
    if lists is None:
        return None

    max_lists = capabilities.get("max_lists")
    max_items_per_list = capabilities.get(
        "max_items_per_list"
    )

    current_lists = len(lists)

    remaining_lists = None
    if max_lists is not None:
        remaining_lists = max(
            max_lists - current_lists,
            0,
        )

    expected_slug = (
        str(tracked_list_name)
        .strip()
        .lower()
        .replace(" ", "-")
    )

    tracked_list = None

    for item in lists:
        if not isinstance(item, dict):
            continue

        name = str(item.get("name") or "").strip()
        ids = item.get("ids", {}) or {}

        if not isinstance(ids, dict):
            ids = {}

        slug = str(ids.get("slug") or "").strip()

        if (
            name.casefold()
            == str(tracked_list_name).strip().casefold()
            or slug.casefold() == expected_slug.casefold()
        ):
            tracked_list = item
            break

    tracked = {
        "name": tracked_list_name,
        "exists": tracked_list is not None,
        "id": None,
        "slug": None,
        "current_items": 0 if tracked_list is None else None,
        "remaining_item_slots": (
            max_items_per_list
            if tracked_list is None
            and max_items_per_list is not None
            else None
        ),
    }

    if tracked_list is not None:
        ids = tracked_list.get("ids", {}) or {}

        if not isinstance(ids, dict):
            ids = {}

        list_id = ids.get("trakt")
        list_slug = ids.get("slug")

        tracked["id"] = list_id
        tracked["slug"] = list_slug

        identifier = list_id or list_slug

        if identifier is None:
            logger.error(
                "Tracked Trakt list has no usable ID or slug: %s",
                tracked_list_name,
            )
            return None

        items = _get_all_trakt_pages(
            f"users/me/lists/{identifier}/items"
        )

        if items is None:
            return None

        current_items = len(items)

        tracked["current_items"] = current_items

        if max_items_per_list is not None:
            tracked["remaining_item_slots"] = max(
                max_items_per_list - current_items,
                0,
            )

    return {
        "username": capabilities.get("username"),
        "vip": capabilities.get("vip"),
        "vip_ep": capabilities.get("vip_ep"),
        "limits_known": capabilities.get("limits_known"),
        "lists": {
            "current": current_lists,
            "maximum": max_lists,
            "remaining": remaining_lists,
        },
        "items_per_list": {
            "maximum": max_items_per_list,
        },
        "tracked_list": tracked,
    }


def assess_trakt_list_creation(
    current_list_count,
    *,
    capabilities=None,
):
    """
    Determine whether the authenticated account can create another
    personal list.

    This function is read-only. Unknown or malformed limits fail closed.
    """
    current = _optional_nonnegative_int(current_list_count)

    if current is None:
        return {
            "allowed": False,
            "reason": "current_list_count_unknown",
            "current": None,
            "maximum": None,
            "remaining": None,
        }

    if capabilities is None:
        capabilities = get_trakt_list_capabilities()

    if not isinstance(capabilities, dict):
        return {
            "allowed": False,
            "reason": "capabilities_unavailable",
            "current": current,
            "maximum": None,
            "remaining": None,
        }

    maximum = _optional_nonnegative_int(
        capabilities.get("max_lists")
    )

    if maximum is None:
        return {
            "allowed": False,
            "reason": "list_limit_unknown",
            "current": current,
            "maximum": None,
            "remaining": None,
        }

    remaining = max(maximum - current, 0)

    return {
        "allowed": current < maximum,
        "reason": (
            "capacity_available"
            if current < maximum
            else "list_limit_reached"
        ),
        "current": current,
        "maximum": maximum,
        "remaining": remaining,
    }


if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(os.path.join(get_data_dir(), "trakt_auth.log")),
            logging.StreamHandler()
        ]
    )
    
    # Simple test of authentication
    console.print("[bold]Testing Trakt.tv authentication...[/bold]")
    access_token = ensure_trakt_auth()
    
    if access_token:
        console.print("[bold green]Authentication successful![/bold green]")
        # Test API access
        config = load_config()
        user = make_trakt_request(f"users/{config['trakt']['username']}")
        if user:
            console.print(f"[green]Successfully accessed Trakt user: {user.get('username')}[/green]")
        else:
            console.print("[bold red]Failed to access Trakt API![/bold red]")
    else:
        console.print("[bold red]Authentication failed![/bold red]")

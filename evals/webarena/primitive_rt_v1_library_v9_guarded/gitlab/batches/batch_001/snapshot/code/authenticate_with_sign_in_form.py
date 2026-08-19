def authenticate_with_sign_in_form(self, base_url: str, username: str, password: str) -> dict:
    import re
    import requests

    if not isinstance(base_url, str) or not base_url.strip():
        raise ValueError("base_url must be a non-empty string")
    if not isinstance(username, str) or not username:
        raise ValueError("username must be a non-empty string")
    if not isinstance(password, str) or not password:
        raise ValueError("password must be a non-empty string")

    base_url = base_url.rstrip("/")
    session = requests.Session()

    sign_in_response = session.get(f"{base_url}/users/sign_in", timeout=30)
    sign_in_response.raise_for_status()
    match = re.search(r'name="authenticity_token" value="([^"]+)"', sign_in_response.text)
    if not match:
        raise RuntimeError("authenticity_token not found on sign-in page")

    response = session.post(
        f"{base_url}/users/sign_in",
        data={
            "authenticity_token": match.group(1),
            "user[login]": username,
            "user[password]": password,
        },
        headers={"Referer": f"{base_url}/users/sign_in"},
        allow_redirects=True,
        timeout=30,
    )
    response.raise_for_status()

    final_url = response.url
    authenticated = "/users/sign_in" not in final_url
    session_established = len(session.cookies) > 0

    return {
        "authenticated": bool(authenticated),
        "final_url": final_url,
        "session_established": bool(session_established),
    }

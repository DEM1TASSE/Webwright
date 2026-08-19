def authenticate_customer_session(self, base_url, email, password):
    import re

    login_url = f"{base_url.rstrip('/')}/customer/account/login/"
    response = self.page.goto(login_url, wait_until="domcontentloaded")
    if response is None:
        raise ValueError("Login navigation produced no response")
    if response.status >= 400:
        raise ValueError(f"Login page returned HTTP {response.status}")

    login_html = self.page.content()
    form_key_match = re.search(r'name="form_key" type="hidden" value="([^"]+)"', login_html)
    if not form_key_match:
        raise ValueError("Login form_key was not found on the login page")

    form_key = form_key_match.group(1)
    post_response = self.page.request.post(
        f"{base_url.rstrip('/')}/customer/account/loginPost/",
        form={
            "form_key": form_key,
            "login[username]": email,
            "login[password]": password,
        },
        headers={"Referer": login_url},
    )
    if post_response.status >= 400:
        raise ValueError(f"Login POST returned HTTP {post_response.status}")

    account_response = self.page.goto(
        f"{base_url.rstrip('/')}/customer/account/",
        wait_until="domcontentloaded",
    )
    if account_response is None:
        raise ValueError("Authenticated account navigation produced no response")
    if account_response.status >= 400:
        raise ValueError(f"Account page returned HTTP {account_response.status}")

    account_html = self.page.content()
    if "Sign Out" not in account_html:
        raise ValueError("Authenticated account indicator 'Sign Out' was not found after login")

    return {
        "authenticated": True,
        "cookie_session_established": True,
    }

def login_customer_account(self, username: str, password: str) -> dict:
    import re
    from urllib.parse import urljoin

    base_url = "http://ec2-18-223-172-69.us-east-2.compute.amazonaws.com:7770/"
    login_url = urljoin(base_url, "customer/account/login/")
    self.page.goto(login_url, wait_until="domcontentloaded")
    html = self.page.content()

    form_match = re.search(r'<form[^>]*id=["\']login-form["\'][\s\S]*?</form>', html, re.I)
    if not form_match:
        raise ValueError("Login form not found")
    form_html = form_match.group(0)

    form_key_match = re.search(r'name=["\']form_key["\'][^>]*value=["\']([^"\']+)["\']', form_html, re.I)
    action_match = re.search(r'action=["\']([^"\']+)["\']', form_html, re.I)
    if not form_key_match:
        raise ValueError("Magento form_key not found")

    form_key = form_key_match.group(1)
    action_url = urljoin(self.page.url, action_match.group(1) if action_match else "customer/account/loginPost/")

    self.page.evaluate(
        """
        async ({actionUrl, formKey, username, password}) => {
            const params = new URLSearchParams();
            params.set('form_key', formKey);
            params.set('login[username]', username);
            params.set('login[password]', password);
            params.set('send', '');
            const response = await fetch(actionUrl, {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: params.toString(),
                credentials: 'same-origin',
                redirect: 'follow'
            });
            await response.text();
        }
        """,
        {"actionUrl": action_url, "formKey": form_key, "username": username, "password": password},
    )
    self.page.goto(urljoin(base_url, "customer/account/"), wait_until="domcontentloaded")

    body_text = self.page.locator("body").inner_text()
    authenticated = (
        "/customer/account/" in self.page.url
        or "Sign Out" in body_text
        or "My Account" in body_text
        or "customer/account/logout" in self.page.content()
    )

    return {
        "authenticated": bool(authenticated),
        "account_url": self.page.url,
        "login_form_action": action_url,
    }

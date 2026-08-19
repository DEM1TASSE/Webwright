def authenticate_customer_graphql(self, base_url: str, email: str, password: str) -> dict:
    import requests

    graphql_url = base_url.rstrip("/") + "/graphql"
    query = (
        "mutation GenerateCustomerToken($email: String!, $password: String!) { "
        "generateCustomerToken(email: $email, password: $password) { token } "
        "}"
    )
    response = requests.post(
        graphql_url,
        json={"query": query, "variables": {"email": email, "password": password}},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    token = (((payload.get("data") or {}).get("generateCustomerToken") or {}).get("token"))
    return {
        "graphql_url": graphql_url,
        "token": token,
        "is_authenticated": bool(token),
    }

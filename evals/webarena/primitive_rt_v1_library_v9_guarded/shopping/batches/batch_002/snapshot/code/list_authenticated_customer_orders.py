def list_authenticated_customer_orders(self, base_url, email, password):
    import requests

    base = base_url.rstrip("/")
    token_response = requests.post(
        f"{base}/rest/V1/integration/customer/token",
        json={"username": email, "password": password},
        timeout=30,
    )
    token_response.raise_for_status()
    token = token_response.json()
    if not isinstance(token, str) or not token:
        raise ValueError("Customer token endpoint did not return a bearer token string")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    query = (
        "query($page:Int!){ customer { firstname lastname email orders(pageSize: 20, currentPage: $page) "
        "{ items { number order_date status total { grand_total { value currency } } } total_count "
        "page_info { current_page total_pages } } } }"
    )

    def _normalize_order(item):
        if not isinstance(item, dict):
            raise ValueError("Each order item must be an object")
        total_obj = item.get("total")
        if not isinstance(total_obj, dict):
            raise ValueError("Order total payload must be an object")
        grand_total = total_obj.get("grand_total")
        if not isinstance(grand_total, dict):
            raise ValueError("Order grand_total payload must be an object")

        value = grand_total.get("value")
        currency = grand_total.get("currency")
        if not isinstance(item.get("number"), str) or not item.get("number"):
            raise ValueError("Order record missing required number")
        if not isinstance(item.get("order_date"), str) or not item.get("order_date"):
            raise ValueError("Order record missing required order_date")
        if not isinstance(item.get("status"), str) or not item.get("status"):
            raise ValueError("Order record missing required status")
        if not isinstance(value, (int, float)):
            raise ValueError("Order record missing numeric grand_total value")
        if not isinstance(currency, str) or not currency:
            raise ValueError("Order record missing grand_total currency")

        return {
            "number": item["number"],
            "order_date": item["order_date"],
            "status": item["status"],
            "total": {
                "grand_total": {
                    "value": value,
                    "currency": currency,
                }
            },
        }

    response = requests.post(
        f"{base}/graphql",
        headers=headers,
        json={"query": query, "variables": {"page": 1}},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()

    customer = payload.get("data", {}).get("customer")
    if not isinstance(customer, dict):
        raise ValueError("Authenticated customer data was not present in GraphQL response")

    orders = customer.get("orders")
    if not isinstance(orders, dict):
        raise ValueError("Customer orders payload was not present in GraphQL response")

    page_info = orders.get("page_info")
    if not isinstance(page_info, dict):
        raise ValueError("Orders page_info payload was not present in GraphQL response")

    current_page_value = page_info.get("current_page")
    total_pages_value = page_info.get("total_pages")
    total_count_value = orders.get("total_count")
    first_items = orders.get("items")

    if not isinstance(current_page_value, int) or current_page_value < 1:
        raise ValueError("Orders page_info.current_page must be a positive integer")
    if not isinstance(total_pages_value, int) or total_pages_value < 1:
        raise ValueError("Orders page_info.total_pages must be a positive integer")
    if not isinstance(total_count_value, int) or total_count_value < 0:
        raise ValueError("Orders total_count must be a non-negative integer")
    if not isinstance(first_items, list):
        raise ValueError("Orders items must be a list")

    result = {
        "customer": {
            "firstname": customer.get("firstname"),
            "lastname": customer.get("lastname"),
            "email": customer.get("email"),
        },
        "orders": [_normalize_order(item) for item in first_items],
        "page_info": {
            "total_count": total_count_value,
            "current_page": current_page_value,
            "total_pages": total_pages_value,
            "pages_fetched": 1,
        },
    }

    if not isinstance(result["customer"]["firstname"], str) or not result["customer"]["firstname"]:
        raise ValueError("Customer firstname was missing")
    if not isinstance(result["customer"]["lastname"], str) or not result["customer"]["lastname"]:
        raise ValueError("Customer lastname was missing")
    if not isinstance(result["customer"]["email"], str) or not result["customer"]["email"]:
        raise ValueError("Customer email was missing")

    page_number = 2
    while page_number <= total_pages_value:
        page_response = requests.post(
            f"{base}/graphql",
            headers=headers,
            json={"query": query, "variables": {"page": page_number}},
            timeout=30,
        )
        page_response.raise_for_status()
        page_payload = page_response.json()

        page_customer = page_payload.get("data", {}).get("customer")
        if not isinstance(page_customer, dict):
            raise ValueError("Authenticated customer data was not present in paginated GraphQL response")
        page_orders = page_customer.get("orders")
        if not isinstance(page_orders, dict):
            raise ValueError("Customer orders payload was not present in paginated GraphQL response")
        page_page_info = page_orders.get("page_info")
        if not isinstance(page_page_info, dict):
            raise ValueError("Orders page_info payload was not present in paginated GraphQL response")

        fetched_current_page = page_page_info.get("current_page")
        fetched_total_pages = page_page_info.get("total_pages")
        items = page_orders.get("items")
        if fetched_current_page != page_number:
            raise ValueError("Paginated GraphQL response current_page did not match requested page")
        if fetched_total_pages != total_pages_value:
            raise ValueError("Paginated GraphQL response total_pages changed during traversal")
        if not isinstance(items, list):
            raise ValueError("Orders items must be a list in paginated GraphQL response")

        result["orders"].extend(_normalize_order(item) for item in items)
        result["page_info"]["pages_fetched"] += 1
        page_number += 1

    return result

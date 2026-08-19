async def multi_search_products_graphql_dedup_by_sku(self, queries: list[str], page_size: int = 100) -> dict:
    import json
    from urllib.parse import quote, urlparse

    if not isinstance(queries, list) or not queries:
        raise ValueError("queries must be a non-empty list of strings")
    if not isinstance(page_size, int) or page_size <= 0:
        raise ValueError("page_size must be a positive integer")
    for query in queries:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("each query must be a non-empty string")

    parsed = urlparse(self.page.url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("self.page.url must contain the shopping site origin before calling this method")
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    merged = {}
    executed_queries = []

    for query in queries:
        graphql_query = (
            '{ products(search:"%s", pageSize:%d) { total_count items { '
            'name sku url_key url_suffix price_range { minimum_price { regular_price { value currency } final_price { value currency } } } } } }'
            % (query.replace('"', '\\"'), page_size)
        )
        graphql_url = base_url + "/graphql?query=" + quote(graphql_query, safe='/:?=&{}"')
        response = await self.page.goto(graphql_url, wait_until="domcontentloaded")
        await self.page.wait_for_load_state("networkidle")
        payload = json.loads(await self.page.locator("body").inner_text())
        products_root = (payload.get("data", {}) or {}).get("products", {}) or {}
        items = products_root.get("items", []) or []

        executed_queries.append({
            "query": query,
            "graphql_url": graphql_url,
            "document_status": response.status if response else None,
            "total_count": products_root.get("total_count"),
            "returned_items_count": len(items),
        })

        for item in items:
            sku = item.get("sku")
            if not sku:
                continue
            minimum_price = (item.get("price_range") or {}).get("minimum_price") or {}
            regular_price = minimum_price.get("regular_price") or {}
            final_price = minimum_price.get("final_price") or {}
            url_key = item.get("url_key")
            url_suffix = item.get("url_suffix")
            merged[sku] = {
                "sku": sku,
                "name": item.get("name"),
                "url_key": url_key,
                "url_suffix": url_suffix,
                "product_url": (base_url + "/" + url_key + (url_suffix or "")) if url_key else None,
                "price_range": {
                    "minimum_price": {
                        "regular_price": {
                            "value": regular_price.get("value"),
                            "currency": regular_price.get("currency"),
                        },
                        "final_price": {
                            "value": final_price.get("value"),
                            "currency": final_price.get("currency"),
                        },
                    }
                },
            }

    records = sorted(merged.values(), key=lambda r: r["sku"])
    return {
        "records": records,
        "executed_queries": executed_queries,
    }

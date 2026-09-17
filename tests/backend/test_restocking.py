"""
Tests for the restocking order endpoints.
"""
import pytest


class TestRestockOrderEndpoints:
    """Test suite for restocking order submission and retrieval."""

    def test_get_restock_orders_returns_list(self, client):
        """Test that the restock orders endpoint returns a list."""
        response = client.get("/api/restock-orders")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_create_restock_order(self, client, reset_restock_orders):
        """Test submitting a valid restocking order."""
        response = client.post("/api/restock-orders", json={
            "lines": [{"sku": "WDG-001", "quantity": 100}],
            "budget": 5000.0,
            "warehouse": "San Francisco",
            "category": "Actuators"
        })
        assert response.status_code == 201

        order = response.json()
        assert order["status"] == "Processing"
        assert order["budget"] == 5000.0
        assert len(order["lines"]) == 1
        assert order["lines"][0]["sku"] == "WDG-001"
        assert order["lines"][0]["quantity"] == 100
        assert order["order_number"].startswith("RST-")

    def test_line_total_uses_inventory_unit_cost(self, client, reset_restock_orders):
        """Test that line totals are priced from inventory, not the request."""
        inventory = client.get("/api/inventory").json()
        item = next(i for i in inventory if i["sku"] == "WDG-001")

        response = client.post("/api/restock-orders", json={
            "lines": [{"sku": "WDG-001", "quantity": 10}],
            "budget": 1000.0
        })
        assert response.status_code == 201

        line = response.json()["lines"][0]
        assert line["unit_cost"] == item["unit_cost"]
        assert line["line_total"] == pytest.approx(10 * item["unit_cost"])

    def test_total_value_sums_all_lines(self, client, reset_restock_orders):
        """Test that the order total is the sum of its line totals."""
        response = client.post("/api/restock-orders", json={
            "lines": [
                {"sku": "WDG-001", "quantity": 10},
                {"sku": "GSK-203", "quantity": 20}
            ],
            "budget": 10000.0
        })
        assert response.status_code == 201

        order = response.json()
        expected = sum(line["line_total"] for line in order["lines"])
        assert order["total_value"] == pytest.approx(expected)

    def test_submitted_order_is_readable(self, client, reset_restock_orders):
        """Test that a submitted order comes back from the GET endpoint."""
        before = len(client.get("/api/restock-orders").json())

        created = client.post("/api/restock-orders", json={
            "lines": [{"sku": "BRG-102", "quantity": 5}],
            "budget": 500.0
        }).json()

        after = client.get("/api/restock-orders").json()
        assert len(after) == before + 1
        assert any(o["order_number"] == created["order_number"] for o in after)

    def test_lead_time_is_positive(self, client, reset_restock_orders):
        """Test that a derived lead time is present and sensible."""
        response = client.post("/api/restock-orders", json={
            "lines": [{"sku": "WDG-001", "quantity": 1}],
            "budget": 100.0,
            "category": "Actuators"
        })
        assert response.status_code == 201

        order = response.json()
        assert order["lead_time_days"] > 0
        assert order["expected_delivery_date"] > order["created_date"]

    def test_unknown_category_still_gets_lead_time(self, client, reset_restock_orders):
        """Test that a category with no order history falls back to a default."""
        response = client.post("/api/restock-orders", json={
            "lines": [{"sku": "WDG-001", "quantity": 1}],
            "budget": 100.0,
            "category": "Nonexistent Category"
        })
        assert response.status_code == 201
        assert response.json()["lead_time_days"] > 0

    def test_empty_order_rejected(self, client, reset_restock_orders):
        """Test that an order with no lines is rejected."""
        response = client.post("/api/restock-orders", json={
            "lines": [],
            "budget": 1000.0
        })
        assert response.status_code == 400
        assert "at least one line" in response.json()["detail"].lower()

    def test_zero_quantity_rejected(self, client, reset_restock_orders):
        """Test that a non-positive quantity is rejected."""
        response = client.post("/api/restock-orders", json={
            "lines": [{"sku": "WDG-001", "quantity": 0}],
            "budget": 1000.0
        })
        assert response.status_code == 400
        assert "greater than zero" in response.json()["detail"].lower()

    def test_unknown_sku_returns_404(self, client, reset_restock_orders):
        """Test that submitting an unknown SKU returns 404."""
        response = client.post("/api/restock-orders", json={
            "lines": [{"sku": "NOPE-999", "quantity": 1}],
            "budget": 1000.0
        })
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_malformed_request_returns_422(self, client, reset_restock_orders):
        """Test that a request missing required fields fails validation."""
        response = client.post("/api/restock-orders", json={"budget": 100.0})
        assert response.status_code == 422

    def test_rejected_order_is_not_recorded(self, client, reset_restock_orders):
        """Test that a failed submission leaves no partial order behind."""
        before = len(client.get("/api/restock-orders").json())

        client.post("/api/restock-orders", json={
            "lines": [
                {"sku": "WDG-001", "quantity": 5},
                {"sku": "NOPE-999", "quantity": 5}
            ],
            "budget": 1000.0
        })

        after = len(client.get("/api/restock-orders").json())
        assert after == before


class TestRestockForecastJoin:
    """Test suite for the forecast-to-inventory join the tab depends on."""

    def test_every_forecast_sku_exists_in_inventory(self, client):
        """Test that all forecast items can be priced from inventory."""
        forecasts = client.get("/api/demand").json()
        inventory = client.get("/api/inventory").json()
        inventory_skus = {item["sku"] for item in inventory}

        missing = [f["item_sku"] for f in forecasts if f["item_sku"] not in inventory_skus]
        assert missing == [], f"forecast SKUs with no inventory record: {missing}"

    def test_forecast_items_have_a_unit_cost(self, client):
        """Test that every forecast item resolves to a usable unit cost."""
        forecasts = client.get("/api/demand").json()
        inventory = {item["sku"]: item for item in client.get("/api/inventory").json()}

        for forecast in forecasts:
            item = inventory[forecast["item_sku"]]
            assert item["unit_cost"] > 0

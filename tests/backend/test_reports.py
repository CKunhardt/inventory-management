"""
Tests for reports API endpoints.
"""
import pytest


QUARTERLY = "/api/reports/quarterly"
MONTHLY = "/api/reports/monthly-trends"


class TestQuarterlyReportEndpoint:
    """Test suite for /api/reports/quarterly."""

    def test_get_quarterly_reports(self, client):
        """Test getting quarterly reports without filters."""
        response = client.get(QUARTERLY)
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 4
        assert [q["quarter"] for q in data] == [
            "Q1-2025", "Q2-2025", "Q3-2025", "Q4-2025"
        ]

    def test_quarterly_structure(self, client):
        """Test that each quarter has all required fields."""
        data = client.get(QUARTERLY).json()

        for quarter in data:
            for field in (
                "quarter", "total_orders", "total_revenue",
                "delivered_orders", "avg_order_value", "fulfillment_rate"
            ):
                assert field in quarter

            assert isinstance(quarter["total_orders"], int)
            assert isinstance(quarter["delivered_orders"], int)
            assert isinstance(quarter["total_revenue"], (int, float))
            assert isinstance(quarter["avg_order_value"], (int, float))
            assert isinstance(quarter["fulfillment_rate"], (int, float))

    def test_quarterly_fulfillment_rate_range(self, client):
        """Test that fulfillment rate is a percentage."""
        for quarter in client.get(QUARTERLY).json():
            assert 0 <= quarter["fulfillment_rate"] <= 100

    def test_quarterly_avg_order_value_calculation(self, client):
        """Test that avg order value matches revenue divided by orders."""
        for quarter in client.get(QUARTERLY).json():
            expected = quarter["total_revenue"] / quarter["total_orders"]
            assert abs(quarter["avg_order_value"] - expected) < 0.01

    def test_quarterly_by_warehouse(self, client):
        """Test filtering quarterly reports by warehouse."""
        response = client.get(f"{QUARTERLY}?warehouse=Tokyo")
        assert response.status_code == 200

        reported = sum(q["total_orders"] for q in response.json())
        actual = len(client.get("/api/orders?warehouse=Tokyo").json())
        assert reported == actual

    def test_quarterly_by_category(self, client):
        """Test filtering quarterly reports by category."""
        response = client.get(f"{QUARTERLY}?category=sensors")
        assert response.status_code == 200

        reported = sum(q["total_orders"] for q in response.json())
        actual = len(client.get("/api/orders?category=sensors").json())
        assert reported == actual

    def test_quarterly_by_status(self, client):
        """Test filtering quarterly reports by status."""
        response = client.get(f"{QUARTERLY}?status=delivered")
        assert response.status_code == 200

        data = response.json()
        # Every remaining order is delivered, so fulfillment is total
        for quarter in data:
            assert quarter["delivered_orders"] == quarter["total_orders"]
            assert quarter["fulfillment_rate"] == 100.0

    def test_quarterly_by_month_narrows_to_one_quarter(self, client):
        """Test that a single-month filter leaves only that month's quarter."""
        response = client.get(f"{QUARTERLY}?month=2025-03")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["quarter"] == "Q1-2025"

    def test_quarterly_by_quarter(self, client):
        """Test that the month filter also accepts a quarter."""
        response = client.get(f"{QUARTERLY}?month=Q2-2025")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["quarter"] == "Q2-2025"

    def test_quarterly_multiple_filters(self, client):
        """Test combining several filters."""
        response = client.get(
            f"{QUARTERLY}?warehouse=Tokyo&category=sensors&status=delivered&month=Q1-2025"
        )
        assert response.status_code == 200

        data = response.json()
        assert len(data) <= 1

        reported = sum(q["total_orders"] for q in data)
        actual = len(client.get(
            "/api/orders?warehouse=Tokyo&category=sensors&status=delivered&month=Q1-2025"
        ).json())
        assert reported == actual

    def test_quarterly_all_is_treated_as_no_filter(self, client):
        """Test that the literal 'all' value does not filter anything out."""
        filtered = client.get(
            f"{QUARTERLY}?warehouse=all&category=all&status=all&month=all"
        ).json()
        unfiltered = client.get(QUARTERLY).json()
        assert filtered == unfiltered

    def test_quarterly_unknown_filter_returns_empty(self, client):
        """Test that a filter matching nothing returns an empty list, not an error."""
        response = client.get(f"{QUARTERLY}?warehouse=Atlantis")
        assert response.status_code == 200
        assert response.json() == []


class TestMonthlyTrendsEndpoint:
    """Test suite for /api/reports/monthly-trends."""

    def test_get_monthly_trends(self, client):
        """Test getting monthly trends without filters."""
        response = client.get(MONTHLY)
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 12

    def test_monthly_trends_structure(self, client):
        """Test that each month has all required fields."""
        for month in client.get(MONTHLY).json():
            for field in ("month", "order_count", "revenue", "delivered_count"):
                assert field in month

            assert isinstance(month["order_count"], int)
            assert isinstance(month["delivered_count"], int)
            assert isinstance(month["revenue"], (int, float))

    def test_monthly_trends_sorted_chronologically(self, client):
        """Test that months come back in order."""
        months = [m["month"] for m in client.get(MONTHLY).json()]
        assert months == sorted(months)

    def test_monthly_trends_month_format(self, client):
        """Test that the month key is YYYY-MM.

        Reports.vue parses this shape to build a localized label.
        """
        for month in client.get(MONTHLY).json():
            assert len(month["month"]) == 7
            assert month["month"].startswith("2025-")

    def test_monthly_trends_by_month(self, client):
        """Test filtering monthly trends to a single month."""
        response = client.get(f"{MONTHLY}?month=2025-03")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["month"] == "2025-03"

    def test_monthly_trends_by_quarter(self, client):
        """Test that a quarter filter leaves that quarter's three months."""
        response = client.get(f"{MONTHLY}?month=Q1-2025")
        assert response.status_code == 200

        months = [m["month"] for m in response.json()]
        assert months == ["2025-01", "2025-02", "2025-03"]

    def test_monthly_trends_by_warehouse(self, client):
        """Test filtering monthly trends by warehouse."""
        response = client.get(f"{MONTHLY}?warehouse=London")
        assert response.status_code == 200

        reported = sum(m["order_count"] for m in response.json())
        actual = len(client.get("/api/orders?warehouse=London").json())
        assert reported == actual

    def test_monthly_trends_multiple_filters(self, client):
        """Test combining several filters."""
        query = "warehouse=Tokyo&category=sensors&status=delivered"
        response = client.get(f"{MONTHLY}?{query}")
        assert response.status_code == 200

        reported = sum(m["order_count"] for m in response.json())
        actual = len(client.get(f"/api/orders?{query}").json())
        assert reported == actual

    def test_monthly_trends_unknown_filter_returns_empty(self, client):
        """Test that a filter matching nothing returns an empty list."""
        response = client.get(f"{MONTHLY}?warehouse=Atlantis")
        assert response.status_code == 200
        assert response.json() == []


class TestReportsCrossValidation:
    """Reports should agree with the raw orders they are derived from."""

    def test_quarterly_and_monthly_agree_on_order_count(self, client):
        """Test that both report endpoints count the same orders."""
        quarterly = sum(q["total_orders"] for q in client.get(QUARTERLY).json())
        monthly = sum(m["order_count"] for m in client.get(MONTHLY).json())
        assert quarterly == monthly

    def test_quarterly_and_monthly_agree_on_revenue(self, client):
        """Test that both report endpoints total the same revenue."""
        quarterly = sum(q["total_revenue"] for q in client.get(QUARTERLY).json())
        monthly = sum(m["revenue"] for m in client.get(MONTHLY).json())
        assert abs(quarterly - monthly) < 0.01

    def test_report_totals_match_orders_endpoint(self, client):
        """Test that report revenue matches the orders it is built from."""
        orders = client.get("/api/orders").json()
        expected = sum(order["total_value"] for order in orders)

        reported = sum(m["revenue"] for m in client.get(MONTHLY).json())
        assert abs(reported - expected) < 0.01

    def test_filters_agree_across_reports_and_orders(self, client):
        """Test that the same filter narrows reports and orders identically."""
        query = "warehouse=Tokyo&month=2025-05"

        orders = client.get(f"/api/orders?{query}").json()
        monthly = client.get(f"{MONTHLY}?{query}").json()

        assert sum(m["order_count"] for m in monthly) == len(orders)
        assert abs(
            sum(m["revenue"] for m in monthly)
            - sum(o["total_value"] for o in orders)
        ) < 0.01

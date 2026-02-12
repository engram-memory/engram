"""Tests for Stripe billing integration."""

from __future__ import annotations

# Ensure cloud mode is off for most tests
import os
from unittest.mock import MagicMock, patch

os.environ.pop("ENGRAM_CLOUD_MODE", None)
os.environ.pop("STRIPE_SECRET_KEY", None)


class TestBillingModels:
    """Test billing route models and validation."""

    def test_price_config_has_tiers(self):
        from server.billing.stripe_client import PRICE_CONFIG

        assert "pro" in PRICE_CONFIG
        assert "enterprise" in PRICE_CONFIG

    def test_pro_pricing(self):
        from server.billing.stripe_client import PRICE_CONFIG

        assert PRICE_CONFIG["pro"]["amount"] == 1490
        assert PRICE_CONFIG["pro"]["currency"] == "eur"

    def test_enterprise_pricing(self):
        from server.billing.stripe_client import PRICE_CONFIG

        assert PRICE_CONFIG["enterprise"]["amount"] == 19900
        assert PRICE_CONFIG["enterprise"]["currency"] == "eur"


class TestStripeClient:
    """Test Stripe client functions with mocked Stripe API."""

    @patch("server.billing.stripe_client.stripe")
    def test_create_customer(self, mock_stripe):
        from server.billing.stripe_client import create_customer

        mock_stripe.Customer.create.return_value = MagicMock(id="cus_test123")
        cid = create_customer("test@test.com", "user-1")
        assert cid == "cus_test123"
        mock_stripe.Customer.create.assert_called_once_with(
            email="test@test.com",
            metadata={"engram_user_id": "user-1"},
        )

    @patch("server.billing.stripe_client.stripe")
    def test_create_checkout_session(self, mock_stripe):
        from server.billing.stripe_client import create_checkout_session, get_price_id

        # Mock price lookup
        mock_stripe.Product.search.return_value = MagicMock(data=[MagicMock(id="prod_1")])
        mock_price = MagicMock(
            id="price_1",
            unit_amount=1490,
            currency="eur",
            recurring=MagicMock(interval="month"),
        )
        mock_stripe.Price.list.return_value = MagicMock(data=[mock_price])

        # Clear cache
        get_price_id.cache_clear()

        mock_stripe.checkout.Session.create.return_value = MagicMock(
            url="https://checkout.stripe.com/xxx"
        )
        url = create_checkout_session("cus_1", "pro", "https://ok", "https://cancel")
        assert url == "https://checkout.stripe.com/xxx"

    @patch("server.billing.stripe_client.stripe")
    def test_create_portal_session(self, mock_stripe):
        from server.billing.stripe_client import create_portal_session

        mock_stripe.billing_portal.Session.create.return_value = MagicMock(
            url="https://portal.stripe.com/xxx"
        )
        url = create_portal_session("cus_1", "https://return")
        assert url == "https://portal.stripe.com/xxx"


class TestWebhookHandlers:
    """Test webhook event handling."""

    def test_handle_checkout_completed(self):
        from server.billing.routes import _handle_checkout_completed

        with patch("server.billing.routes.db") as mock_db:
            mock_db.get_user_by_stripe_customer_id.return_value = {"id": "user-1", "tier": "free"}
            _handle_checkout_completed(
                {
                    "customer": "cus_1",
                    "subscription": "sub_1",
                    "metadata": {"engram_tier": "pro"},
                }
            )
            mock_db.update_user_tier.assert_called_once_with("user-1", "pro")
            mock_db.update_stripe_subscription_id.assert_called_once_with("user-1", "sub_1")

    def test_handle_subscription_deleted(self):
        from server.billing.routes import _handle_subscription_deleted

        with patch("server.billing.routes.db") as mock_db:
            mock_db.get_user_by_stripe_customer_id.return_value = {"id": "user-1", "tier": "pro"}
            _handle_subscription_deleted({"customer": "cus_1"})
            mock_db.update_user_tier.assert_called_once_with("user-1", "free")
            mock_db.update_stripe_subscription_id.assert_called_once_with("user-1", None)

    def test_handle_checkout_no_user(self):
        from server.billing.routes import _handle_checkout_completed

        with patch("server.billing.routes.db") as mock_db:
            mock_db.get_user_by_stripe_customer_id.return_value = None
            # Should not raise
            _handle_checkout_completed(
                {
                    "customer": "cus_unknown",
                    "subscription": "sub_1",
                    "metadata": {"engram_tier": "pro"},
                }
            )
            mock_db.update_user_tier.assert_not_called()

    def test_handle_payment_failed(self):
        from server.billing.routes import _handle_payment_failed

        with patch("server.billing.routes.db") as mock_db:
            mock_db.get_user_by_stripe_customer_id.return_value = {"id": "user-1"}
            # Should not raise (just logs for now)
            _handle_payment_failed({"customer": "cus_1"})


class TestDatabaseStripeFields:
    """Test new Stripe fields in admin database."""

    def setup_method(self):
        from server.auth.database import create_user, init_admin_db, set_admin_db_path

        self.db_path = "/tmp/test_billing_admin.db"
        import pathlib

        pathlib.Path(self.db_path).unlink(missing_ok=True)
        set_admin_db_path(self.db_path)
        init_admin_db()
        create_user("user-1", "test@test.com", "hash123")

    def teardown_method(self):
        import pathlib

        pathlib.Path(self.db_path).unlink(missing_ok=True)

    def test_update_stripe_customer_id(self):
        from server.auth.database import get_user_by_id, update_stripe_customer_id

        update_stripe_customer_id("user-1", "cus_test123")
        user = get_user_by_id("user-1")
        assert user["stripe_customer_id"] == "cus_test123"

    def test_update_stripe_subscription_id(self):
        from server.auth.database import get_user_by_id, update_stripe_subscription_id

        update_stripe_subscription_id("user-1", "sub_test123")
        user = get_user_by_id("user-1")
        assert user["stripe_subscription_id"] == "sub_test123"

    def test_get_user_by_stripe_customer_id(self):
        from server.auth.database import get_user_by_stripe_customer_id, update_stripe_customer_id

        update_stripe_customer_id("user-1", "cus_test456")
        user = get_user_by_stripe_customer_id("cus_test456")
        assert user is not None
        assert user["id"] == "user-1"

    def test_get_user_by_stripe_customer_id_not_found(self):
        from server.auth.database import get_user_by_stripe_customer_id

        user = get_user_by_stripe_customer_id("cus_nonexistent")
        assert user is None

    def test_clear_subscription_id(self):
        from server.auth.database import get_user_by_id, update_stripe_subscription_id

        update_stripe_subscription_id("user-1", "sub_123")
        update_stripe_subscription_id("user-1", None)
        user = get_user_by_id("user-1")
        assert user["stripe_subscription_id"] is None

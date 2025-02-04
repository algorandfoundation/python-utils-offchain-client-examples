from typing import NamedTuple
import pytest
from algokit_utils import *
from algokit_utils.config import config

from smart_contracts.artifacts.auction.auction_client import (
    AuctionClient,
    AuctionFactory,
    CommonAppCallParams,
    StartAuctionArgs,
)


class LocalTestAccounts(NamedTuple):
    creator: SigningAccount
    alice: SigningAccount
    bob: SigningAccount


class AuctionClients(NamedTuple):
    creator: AuctionClient
    alice: AuctionClient
    bob: AuctionClient


@pytest.fixture(scope="session")
def algorand() -> AlgorandClient:
    """Get an AlgorandClient to use throughout the tests"""
    algorand = AlgorandClient.default_localnet()
    algorand.set_default_validity_window(1000)

    return algorand


@pytest.fixture(scope="session")
def dispenser(algorand: AlgorandClient) -> SigningAccount:
    """Get the dispenser to fund test addresses"""
    return algorand.account.localnet_dispenser()


@pytest.fixture(scope="session")
def test_accounts(
    algorand: AlgorandClient, dispenser: SigningAccount
) -> LocalTestAccounts:
    """Get an account to use as the creator of the auction"""

    accounts = LocalTestAccounts(
        creator=algorand.account.random(),
        alice=algorand.account.random(),
        bob=algorand.account.random(),
    )

    # Make sure the accounts have some ALGO
    for account in accounts:
        algorand.send.payment(
            params=PaymentParams(
                sender=dispenser.address,
                receiver=account.address,
                amount=AlgoAmount({"algos": 10}),
            )
        )

    return accounts


@pytest.fixture(scope="session")
def auction_asset_id(test_accounts: LocalTestAccounts, algorand: AlgorandClient) -> int:
    """Create an asset to be auctioned"""
    # Create an asset
    sent_txn = algorand.send.asset_create(
        AssetCreateParams(
            sender=test_accounts.creator.address,
            total=1,
            decimals=0,
            asset_name="Mona Lisa",
            unit_name="ML",
            url="https://path/to/my/asset/details",
        )
    )

    print(f"Asset created with ID: {sent_txn}")

    # Make sure the network tells us the ID of the asset we just created
    return sent_txn.asset_id


@pytest.fixture(scope="session")
def auction_app_factory(
    test_accounts: LocalTestAccounts, algorand: AlgorandClient
) -> AppFactory:
    """Define the Auction App Factory"""

    config.configure(
        debug=True,
        # trace_all=True,
    )

    app_factory = algorand.client.get_typed_app_factory(
        typed_factory=AuctionFactory,
        app_name="auction",
        default_sender=test_accounts.creator.address,
        default_signer=test_accounts.creator.signer,
        version="1.0",
        compilation_params=AppClientCompilationParams(
            updatable=False,
            deletable=False,
        ),
    )

    return app_factory


@pytest.fixture(scope="session")
def auction_clients(
    test_accounts: LocalTestAccounts,
    algorand: AlgorandClient,
    auction_app_factory: AppFactory,
) -> AuctionClients:
    """Deploy an Auction App and create an Auction app client the creator will use"""

    creator_app_client, deploy_result = auction_app_factory.deploy(
        on_update=OnUpdate.ReplaceApp,
        on_schema_break=OnSchemaBreak.Fail,
    )

    algorand.send.payment(
        params=PaymentParams(
            sender=test_accounts.creator.address,
            receiver=creator_app_client.app_address,
            amount=AlgoAmount({"algos": 1}),  # 1 Algo
        )
    )

    alice_app_client = auction_app_factory.get_app_client_by_id(
        app_id=creator_app_client.app_id,
        default_sender=test_accounts.alice.address,
        default_signer=test_accounts.alice.signer,
    )

    bob_app_client = auction_app_factory.get_app_client_by_id(
        app_id=creator_app_client.app_id,
        default_sender=test_accounts.bob.address,
        default_signer=test_accounts.bob.signer,
    )

    print(f"creator app client details {creator_app_client.app_id}")
    return AuctionClients(creator_app_client, alice_app_client, bob_app_client)


def test_opt_into_asset(
    auction_clients: AuctionClients,
    test_accounts: LocalTestAccounts,
    auction_asset_id: int,
    algorand: AlgorandClient,
) -> None:
    """Test that the auction app opts into the auction asset"""

    # Reset timestamp offset to ensure it's current time in localnet
    algorand.client.algod.set_timestamp_offset(0)

    creator_app_client = auction_clients.creator

    # dummy transaction to update the timestamp offset
    algorand.send.payment(
        PaymentParams(
            sender=test_accounts.creator.address,
            receiver=test_accounts.creator.address,
            amount=AlgoAmount({"microAlgos": 0}),
        )
    )

    creator_app_client.send.opt_into_asset(
        args=(auction_asset_id,),
        params=CommonAppCallParams(extra_fee=AlgoAmount({"microAlgos": 1000})),
    )

    account_info = algorand.account.get_information(creator_app_client.app_address)
    print(f"account_info.assets: {account_info.assets}")

    assert account_info.assets[0]["asset-id"] == auction_asset_id
    assert account_info.assets[0]["amount"] == 0


def test_start_auction(
    auction_clients: AuctionClients,
    test_accounts: LocalTestAccounts,
    auction_asset_id: int,
    algorand: AlgorandClient,
) -> None:
    """Test that the auction is started"""
    asa_transfer_txn = algorand.create_transaction.asset_transfer(
        AssetTransferParams(
            sender=test_accounts.creator.address,
            receiver=auction_clients.creator.app_address,
            asset_id=auction_asset_id,
            amount=1,
        )
    )

    start_timestamp = auction_clients.creator.send.start_auction(
        args=StartAuctionArgs(
            starting_price=1000000,
            length=1000,
            axfer=asa_transfer_txn,
        )
    )
    print(f"Auction started at Unix time: {start_timestamp.abi_return}\n")

    assert start_timestamp.abi_return


def test_alice_bid(
    auction_clients: AuctionClients,
    test_accounts: LocalTestAccounts,
    auction_asset_id: int,
    algorand: AlgorandClient,
) -> None:
    """Test that Alice bids in the auction"""

    # Alice opts into the auction asset (ASA)
    algorand.send.asset_opt_in(
        AssetOptInParams(
            sender=test_accounts.alice.address,
            asset_id=auction_asset_id,
        )
    )

    auction_clients.alice.send.opt_in.opt_in()

    alice_bid_payment_txn = algorand.create_transaction.payment(
        PaymentParams(
            sender=test_accounts.alice.address,
            receiver=auction_clients.alice.app_address,
            amount=AlgoAmount({"microAlgos": 1100000}),
        )
    )

    highest_bid = auction_clients.alice.send.bid(args=(alice_bid_payment_txn,))
    print(
        f"Alice is the highest bidder with bid: {highest_bid.abi_return} microAlgos\n"
    )

    alice_local_state = auction_clients.alice.app_client.get_local_state(
        test_accounts.alice.address
    )

    print(f"alice_local_state: {alice_local_state}")

    assert alice_local_state["claim"].value == 1100000


def test_bob_bid(
    auction_clients: AuctionClients,
    test_accounts: LocalTestAccounts,
    auction_asset_id: int,
    algorand: AlgorandClient,
) -> None:
    """Test that Bob outbids Alice in the auction"""

    # Alice opts into the auction asset (ASA)
    algorand.send.asset_opt_in(
        AssetOptInParams(
            sender=test_accounts.bob.address,
            asset_id=auction_asset_id,
        )
    )

    auction_clients.bob.send.opt_in.opt_in()

    bob_bid_payment_txn = algorand.create_transaction.payment(
        PaymentParams(
            sender=test_accounts.bob.address,
            receiver=auction_clients.bob.app_address,
            amount=AlgoAmount({"microAlgos": 2000000}),
        )
    )

    highest_bid = auction_clients.bob.send.bid(args=(bob_bid_payment_txn,))
    print(f"Bob is the highest bidder with bid: {highest_bid.abi_return} microAlgos\n")

    bob_local_state = auction_clients.bob.app_client.get_local_state(
        test_accounts.bob.address
    )

    assert bob_local_state["claim"].value == 2000000


def test_alice_claim_bid(
    auction_clients: AuctionClients,
) -> None:
    """Test that Alice claims her bid"""

    claimed_amount = auction_clients.alice.send.claim_bids(
        params=CommonAppCallParams(extra_fee=AlgoAmount({"microAlgos": 1000}))
    )
    assert claimed_amount.abi_return == 1100000


def test_bob_claim_prize(
    auction_clients: AuctionClients,
    test_accounts: LocalTestAccounts,
    auction_asset_id: int,
    algorand: AlgorandClient,
) -> None:
    """Test that Bob claims the prize"""

    algorand.client.algod.set_timestamp_offset(1001)

    algorand.send.payment(
        PaymentParams(
            sender=test_accounts.bob.address,
            receiver=test_accounts.bob.address,
            amount=AlgoAmount({"microAlgos": 0}),
        )
    )

    auction_clients.bob.send.claim_asset(
        args=(auction_asset_id,),
        params=CommonAppCallParams(extra_fee=AlgoAmount({"microAlgos": 1000})),
    )

    bob_asset_info = algorand.account.get_information(test_accounts.bob.address)
    assert bob_asset_info.assets[0]["asset-id"] == auction_asset_id
    assert bob_asset_info.assets[0]["amount"] == 1


def test_delete_app(
    auction_clients: AuctionClients,
    test_accounts: LocalTestAccounts,
    algorand: AlgorandClient,
) -> None:
    """Test that the creator claims the prize fund and deletes the auction app"""

    auction_clients.creator.send.delete.delete_application(
        params=CommonAppCallParams(extra_fee=AlgoAmount({"microAlgos": 1000}))
    )
    creator_info = algorand.account.get_information(test_accounts.creator.address)

    assert creator_info.total_created_apps == 0

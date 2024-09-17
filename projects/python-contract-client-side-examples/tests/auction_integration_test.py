import pytest
from algokit_utils import TransactionParameters
from algokit_utils.beta.account_manager import AddressAndSigner
from algokit_utils.beta.algorand_client import (
    AlgorandClient,
    AssetCreateParams,
    AssetOptInParams,
    AssetTransferParams,
    PayParams,
)
from algokit_utils.config import config
from algosdk.atomic_transaction_composer import TransactionWithSigner
from algosdk.v2client.algod import AlgodClient

from smart_contracts.artifacts.auction.auction_client import AuctionClient


@pytest.fixture(scope="session")
def algorand() -> AlgorandClient:
    """Get an AlgorandClient to use throughout the tests"""
    algorand = AlgorandClient.default_local_net()
    algorand.set_default_validity_window(1000)

    return algorand


@pytest.fixture(scope="session")
def dispenser(algorand: AlgorandClient) -> AddressAndSigner:
    """Get the dispenser to fund test addresses"""
    return algorand.account.dispenser()


@pytest.fixture(scope="session")
def creator(algorand: AlgorandClient, dispenser: AddressAndSigner) -> AddressAndSigner:
    """Get an account to use as the creator of the auction"""
    acct = algorand.account.random()

    # Make sure the account has some ALGO
    algorand.send.payment(
        PayParams(sender=dispenser.address, receiver=acct.address, amount=10_000_000)
    )

    return acct


@pytest.fixture(scope="session")
def alice(algorand: AlgorandClient, dispenser: AddressAndSigner) -> AddressAndSigner:
    """Get an account to use as Alice who will participate in the auction"""
    acct = algorand.account.random()

    # Make sure the account has some ALGO
    algorand.send.payment(
        PayParams(sender=dispenser.address, receiver=acct.address, amount=10_000_000)
    )

    return acct


@pytest.fixture(scope="session")
def bob(algorand: AlgorandClient, dispenser: AddressAndSigner) -> AddressAndSigner:
    """Get an account to use as Bob who will participate in the auction"""

    acct = algorand.account.random()

    # Make sure the account has some ALGO
    algorand.send.payment(
        PayParams(sender=dispenser.address, receiver=acct.address, amount=10_000_000)
    )

    return acct


@pytest.fixture(scope="session")
def auction_asset_id(creator: AddressAndSigner, algorand: AlgorandClient) -> int:
    """Create an asset to be auctioned"""
    # Create an asset
    sent_txn = algorand.send.asset_create(
        AssetCreateParams(
            sender=creator.address,
            total=1,
            decimals=0,
            asset_name="Mona Lisa",
            unit_name="ML",
            url="https://path/to/my/asset/details",
        )
    )

    # Make sure the network tells us the ID of the asset we just created
    return sent_txn["confirmation"]["asset-index"]


@pytest.fixture(scope="session")
def creator_auction_client(
    algod_client: AlgodClient, creator: AddressAndSigner, algorand: AlgorandClient
) -> AuctionClient:
    """Deploy an Auction App and create an Auction app client the creator will use"""

    config.configure(
        debug=True,
        # trace_all=True,
    )

    auction_client = AuctionClient(
        algod_client,
        sender=creator.address,
        signer=creator.signer,
    )

    auction_client.create_bare()

    algorand.send.payment(
        PayParams(
            sender=creator.address,
            receiver=auction_client.app_address,
            amount=1000000,  # 1 Algo
        )
    )

    print(f"creator app client details {auction_client.app_id}")
    return auction_client


@pytest.fixture(scope="session")
def alice_auction_client(
    algod_client: AlgodClient,
    creator_auction_client: AuctionClient,
    alice: AddressAndSigner,
) -> AuctionClient:
    """Create an Auction App Client for Alice"""

    config.configure(
        debug=True,
        # trace_all=True,
    )

    auction_client = AuctionClient(
        algod_client,
        sender=alice.address,
        signer=alice.signer,
        app_id=creator_auction_client.app_id,
    )
    print(f"Alice app client details {auction_client.app_id}")

    return auction_client


@pytest.fixture(scope="session")
def bob_auction_client(
    algod_client: AlgodClient,
    creator_auction_client: AuctionClient,
    bob: AddressAndSigner,
) -> AuctionClient:
    """Create an Auction App Client for Bob"""

    config.configure(
        debug=True,
        # trace_all=True,
    )

    auction_client = AuctionClient(
        algod_client,
        sender=bob.address,
        signer=bob.signer,
        app_id=creator_auction_client.app_id,
    )
    print(f"Bob app client details {auction_client.app_id}")

    return auction_client


def test_opt_into_asset(
    algod_client: AlgodClient,
    creator_auction_client: AuctionClient,
    creator: AddressAndSigner,
    auction_asset_id: int,
    algorand: AlgorandClient,
) -> None:
    """Test that the auction app opts into the auction asset"""

    # Reset timestamp offset to ensure it's current time in localnet
    algod_client.set_timestamp_offset(0)

    # dummy transaction to update the timestamp offset
    algorand.send.payment(
        PayParams(
            sender=creator.address,
            receiver=creator.address,
            amount=0,
        )
    )

    sp = algod_client.suggested_params()
    sp.flat_fee = True
    sp.fee = 2000

    creator_auction_client.opt_into_asset(
        asset=auction_asset_id,
        transaction_parameters=TransactionParameters(suggested_params=sp),
    )

    asset_info = algorand.account.get_asset_information(
        creator_auction_client.app_address, auction_asset_id
    )

    assert asset_info["asset-holding"]["asset-id"] == auction_asset_id
    assert asset_info["asset-holding"]["amount"] == 0


def test_start_auction(
    creator_auction_client: AuctionClient,
    creator: AddressAndSigner,
    auction_asset_id: int,
    algorand: AlgorandClient,
) -> None:
    """Test that the auction is started"""
    asa_transfer_txn = algorand.transactions.asset_transfer(
        AssetTransferParams(
            sender=creator.address,
            receiver=creator_auction_client.app_address,
            asset_id=auction_asset_id,
            amount=1,
        )
    )

    signed_asa_transfer_txn = TransactionWithSigner(asa_transfer_txn, creator.signer)

    start_timestamp = creator_auction_client.start_auction(
        starting_price=1000000, length=1000, axfer=signed_asa_transfer_txn
    )
    print(f"Auction started at Unix time: {start_timestamp.return_value}\n")

    assert start_timestamp.return_value


def test_alice_bid(
    alice_auction_client: AuctionClient,
    alice: AddressAndSigner,
    auction_asset_id: int,
    algorand: AlgorandClient,
) -> None:
    """Test that Alice bids in the auction"""

    # Alice opts into the auction asset (ASA)
    algorand.send.asset_opt_in(
        AssetOptInParams(
            sender=alice.address,
            asset_id=auction_asset_id,
        )
    )

    alice_auction_client.opt_in_opt_in()

    alice_bid_payment_txn = algorand.transactions.payment(
        PayParams(
            sender=alice.address,
            receiver=alice_auction_client.app_address,
            amount=1100000,
        )
    )

    alice_bid_payment_tws = TransactionWithSigner(alice_bid_payment_txn, alice.signer)

    highest_bid = alice_auction_client.bid(pay=alice_bid_payment_tws)
    print(
        f"Alice is the highest bidder with bid: {highest_bid.return_value} microAlgos\n"
    )

    alice_local_state = alice_auction_client.get_local_state(alice.address)

    assert alice_local_state.claimable_amount == 1100000


def test_bob_bid(
    bob_auction_client: AuctionClient,
    bob: AddressAndSigner,
    auction_asset_id: int,
    algorand: AlgorandClient,
) -> None:
    """Test that Bob outbids Alice in the auction"""

    # Alice opts into the auction asset (ASA)
    algorand.send.asset_opt_in(
        AssetOptInParams(
            sender=bob.address,
            asset_id=auction_asset_id,
        )
    )

    bob_auction_client.opt_in_opt_in()

    bob_bid_payment_txn = algorand.transactions.payment(
        PayParams(
            sender=bob.address,
            receiver=bob_auction_client.app_address,
            amount=2000000,
        )
    )

    bob_bid_payment_tws = TransactionWithSigner(bob_bid_payment_txn, bob.signer)

    highest_bid = bob_auction_client.bid(pay=bob_bid_payment_tws)
    print(
        f"Bob is the highest bidder with bid: {highest_bid.return_value} microAlgos\n"
    )

    bob_local_state = bob_auction_client.get_local_state(bob.address)

    assert bob_local_state.claimable_amount == 2000000


def test_alice_claim_bid(
    algod_client: AlgodClient,
    alice_auction_client: AuctionClient,
) -> None:
    """Test that Alice claims her bid"""

    sp = algod_client.suggested_params()
    sp.flat_fee = True
    sp.fee = 2000

    claimed_amount = alice_auction_client.claim_bids(
        transaction_parameters=TransactionParameters(suggested_params=sp)
    )
    assert claimed_amount.return_value == 1100000


def test_bob_claim_prize(
    algod_client: AlgodClient,
    bob_auction_client: AuctionClient,
    bob: AddressAndSigner,
    auction_asset_id: int,
    algorand: AlgorandClient,
) -> None:
    """Test that Bob claims the prize"""

    algod_client.set_timestamp_offset(1001)

    algorand.send.payment(
        PayParams(
            sender=bob.address,
            receiver=bob.address,
            amount=0,
        )
    )

    sp = algod_client.suggested_params()
    sp.flat_fee = True
    sp.fee = 2000  # double fee to cover inner txn fee

    bob_auction_client.claim_asset(
        asset=auction_asset_id,
        transaction_parameters=TransactionParameters(suggested_params=sp),
    )

    bob_asset_info = algorand.account.get_asset_information(
        bob.address, auction_asset_id
    )
    assert bob_asset_info["asset-holding"]["asset-id"] == auction_asset_id
    assert bob_asset_info["asset-holding"]["amount"] == 1


def test_delete_app(
    algod_client: AlgodClient,
    creator_auction_client: AuctionClient,
    creator: AddressAndSigner,
    algorand: AlgorandClient,
) -> None:
    """Test that the creator claims the prize fund and deletes the auction app"""

    sp = algod_client.suggested_params()
    sp.flat_fee = True
    sp.fee = 2000  # double fee to cover inner txn fee

    creator_auction_client.delete_delete_application(
        transaction_parameters=TransactionParameters(suggested_params=sp)
    )
    creator_info = algorand.account.get_information(creator.address)

    assert creator_info["total-created-apps"] == 0

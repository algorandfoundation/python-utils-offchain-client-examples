# type: ignore

import logging

import algokit_utils
from algokit_utils import TransactionParameters
from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.indexer import IndexerClient
from algosdk.transaction import AssetConfigTxn, PaymentTxn
from algosdk.atomic_transaction_composer import (
    AtomicTransactionComposer,
    TransactionWithSigner,
)
import algosdk

logger = logging.getLogger(__name__)


# define deployment behaviour based on supplied app spec
def deploy(
    algod_client: AlgodClient,
    indexer_client: IndexerClient,
    app_spec: algokit_utils.ApplicationSpecification,
    deployer: algokit_utils.Account,
) -> None:
    from smart_contracts.artifacts.auction.auction_client import (
        AuctionClient,
    )
    print("### Lifecycle of the Auction Contract ###")

    # Reset timestamp offset
    algod_client.set_timestamp_offset(0)
    print(f"Current timestamp offset: {algod_client.get_timestamp_offset()}\n")

    print("Deployer address", deployer.address)
    
    # Create accounts who will bid on the auction
    alice = algokit_utils.get_account(
        client=algod_client, name="Alice", fund_with_algos=100
    )
    print("Alice address", alice.address)
    bob = algokit_utils.get_account(
        client=algod_client, name="Bob", fund_with_algos=100
    )
    print(f"Bob address {bob.address}\n")
    
    # Create auction asset
    print("## Creating auction asset ##")
    sp = algod_client.suggested_params()
    asa_create_txn = AssetConfigTxn(
        sender=deployer.address,
        sp=sp,
        total=1,
        decimals=0,
        default_frozen=False,
        unit_name="ML",
        asset_name="Mona Lisa",
        url="https://path/to/my/asset/details",
        manager="",
        reserve="",
        freeze="",
        clawback="",
        strict_empty_address_check=False,
    )
    results = execute_transaction(algod_client, asa_create_txn, deployer)
    print(f"ASA created in round: {results['confirmed-round']}")

    auction_asa_id = results["asset-index"]
    print(f"Asset ID: {auction_asa_id}\n")

    print("## Deploying Auction Contract ##")
    app_client = AuctionClient(
        algod_client,
        creator=deployer,
        indexer_client=indexer_client,
    )

    app_client.app_client.create()
    print(f"app id {app_client.app_id}")
    print(f"app address {app_client.app_address}\n")

    print("## opt_into_asset ##\n")
    # add payment transaction to the atc to fund the contract
    atc = AtomicTransactionComposer()

    sp = algod_client.suggested_params()
    fund_contract_payment_txn = PaymentTxn(
        sender=deployer.address,
        sp=sp,
        receiver=app_client.app_address,
        amt=1000000,  # 1 Algo
    )

    tws = TransactionWithSigner(fund_contract_payment_txn, deployer.signer)
    atc.add_transaction(tws)

    # # opt_into_asset has an inner txn. doubling txn fee to cover the inner txn fee
    sp = algod_client.suggested_params()
    sp.flat_fee = True
    sp.fee = 2000

    # add opt_into_asset method call to the atc
    atc.add_method_call(
        app_id=app_client.app_id,
        method=app_spec.contract.get_method_by_name("opt_into_asset"),
        sender=deployer.address,
        sp=sp,
        signer=deployer.signer,
        method_args=[auction_asa_id],
    )
    atc.execute(algod_client, 4)
    print("opt_into_asset confirmed\n")

    print("## Start Auction ##")
    # Creator start auction
    sp = algod_client.suggested_params()
    asa_transfer_txn = algosdk.transaction.AssetTransferTxn(
        sender=deployer.address,
        sp=sp,
        receiver=app_client.app_address,
        amt=1,
        index=auction_asa_id,
    )

    signed_asa_transfer_txn = TransactionWithSigner(asa_transfer_txn, deployer.signer)

    start_timestamp = app_client.start_auction(
        starting_price=1000000, length=1000, axfer=signed_asa_transfer_txn
    )
    print(f"Auction started at Unix time: {start_timestamp.return_value}\n")

    print("## Alice bids ##")
    # Alice opts in and bid (zero transfer to one's self is an asset opt in transaction)
    alice_optin_asset_txn = algosdk.transaction.AssetTransferTxn(
        sender=alice.address,
        sp=sp,
        receiver=alice.address,
        amt=0,
        index=auction_asa_id,
    )
    results = execute_transaction(algod_client, alice_optin_asset_txn, alice)
    print(f"Alice optin to asset confirmed in round: {results['confirmed-round']}")

    # Create Alice's app client

    alice_app_client = AuctionClient(
        algod_client,
        signer=alice,
        app_id=app_client.app_id,
    )

    alice_app_client.opt_in_opt_in()

    sp = algod_client.suggested_params()
    alice_bid_payment_txn = PaymentTxn(
        sender=alice.address,
        sp=sp,
        receiver=app_client.app_address,
        amt=1100000,
    )

    alice_bid_payment_tws = TransactionWithSigner(alice_bid_payment_txn, alice.signer)

    highest_bid = alice_app_client.bid(pay=alice_bid_payment_tws)
    print(f"Alice is the highest bidder with bid: {highest_bid.return_value} microAlgos\n")

    # Get Auction State
    app_global_state_info = algod_client.application_info(app_client.app_id)
    print("global state info", app_global_state_info["params"]["global-state"])

    app_local_state_info = algod_client.account_application_info(
        alice.address, app_client.app_id
    )
    print(f"local state info {app_local_state_info["app-local-state"]["key-value"]}\n")

    print("## Bob outbids Alice ##")
    # Bob opts in and bid higher
    bob_optin_asset_txn = algosdk.transaction.AssetTransferTxn(
        sender=bob.address,
        sp=sp,
        receiver=bob.address,
        amt=0,
        index=auction_asa_id,
    )
    results = execute_transaction(algod_client, bob_optin_asset_txn, bob)
    print(f"Bob optin to asset confirmed in round: {results['confirmed-round']}")

    # Create Bob's app client
    bob_app_client = AuctionClient(
        algod_client,
        signer=bob,
        app_id=app_client.app_id,
    )

    bob_app_client.opt_in_opt_in()

    sp = algod_client.suggested_params()
    bob_bid_payment_txn = PaymentTxn(
        sender=bob.address,
        sp=sp,
        receiver=app_client.app_address,
        amt=2000000, # Bids 2 Algos
    )

    bob_bid_payment_tws = TransactionWithSigner(bob_bid_payment_txn, bob.signer)

    # Bob bids
    highest_bid = bob_app_client.bid(pay=bob_bid_payment_tws)
    print(f"Bob is the highest bidder with bid: {highest_bid.return_value} microAlgos\n")

    # Get Auction State
    app_global_state_info = algod_client.application_info(app_client.app_id)
    print("global state info", app_global_state_info["params"]["global-state"])
    
    app_local_state_info = algod_client.account_application_info(
        alice.address, app_client.app_id
    )
    print(f"local state info {app_local_state_info["app-local-state"]["key-value"]}\n")

    print("## Alice claims bid ##")
    sp = algod_client.suggested_params()
    sp.flat_fee = True
    sp.fee = 2000

    claimed_amount = alice_app_client.claim_bids(transaction_parameters=TransactionParameters(suggested_params=sp))
    print(f"Alice claimed {claimed_amount.return_value} microAlgos\n")

    print("## Bob claim prize ##")
    # Set timestamp offset in mainnet to fastforward 1000 unix time
    algod_client.set_timestamp_offset(1001)
    current_timestamp = algod_client.get_timestamp_offset()
    print("current timestamp Offset", current_timestamp) 

    # Send dummy txn to submit a new block and update latest_timestamp
    sp = algod_client.suggested_params()
    dummy_txn = PaymentTxn(
        sender=deployer.address,
        sp=sp,
        receiver=deployer.address,
        amt=0,
    )
    execute_transaction(algod_client, dummy_txn, deployer)

    # Bob claim prize(asset)
    sp = algod_client.suggested_params()
    sp.flat_fee = True
    sp.fee = 2000 # double fee to cover inner txn fee

    bob_app_client.claim_asset(asset=auction_asa_id, transaction_parameters=TransactionParameters(suggested_params=sp))
    print(f"Bob claimed the auction asset")

    bob_asset_info = algod_client.account_asset_info(bob.address, auction_asa_id)
    print(f"Bob's asset info: {bob_asset_info}\n")

    print("## Creator claim prize funds and delele the auction app ##")
    # Creator Delete app
    sp = algod_client.suggested_params()
    sp.flat_fee = True
    sp.fee = 2000 # double fee to cover inner txn fee
    app_client.delete_delete_application(transaction_parameters=TransactionParameters(suggested_params=sp))
    print("App deleted")

def execute_transaction(
    algod_client: AlgodClient,
    txn: algosdk.transaction.Transaction,
    sender: algokit_utils.Account,
) -> dict:
    # Sign with secret key of manager
    stxn = txn.sign(sender.private_key)

    # Send the transaction to the network and retrieve the txid.
    txid = algod_client.send_transaction(stxn)
    print(f"Sent transaction with txid: {txid}")

    # Wait for the transaction to be confirmed
    results = algosdk.transaction.wait_for_confirmation(algod_client, txid, 4)
    return results

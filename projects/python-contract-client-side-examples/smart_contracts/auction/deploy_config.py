# type: ignore

import logging

import algokit_utils
from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.indexer import IndexerClient

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

    # Reset timestamp offset
    algod_client.set_timestamp_offset(0)
    print(f"Current timestamp offset: {algod_client.get_timestamp_offset()}\n")

    app_client = AuctionClient(
        algod_client,
        creator=deployer,
        indexer_client=indexer_client,
    )

    app_client.app_client.create()
    print(f"app id {app_client.app_id}")
    print(f"app address {app_client.app_address}\n")

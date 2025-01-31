import algokit_utils
import pytest
from algokit_utils import *
from algokit_utils.config import config
from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.indexer import IndexerClient

from smart_contracts.artifacts.hello_world.hello_world_client import (
    HelloWorldFactory,
    HelloWorldClient,
)


@pytest.fixture(scope="session")
def hello_world_client() -> HelloWorldClient:
    config.configure(
        debug=True,
        # trace_all=True,
    )

    algorand = AlgorandClient.default_localnet()

    deployer = algorand.account.random()
    algorand.account.ensure_funded(
        account_to_fund=deployer,
        dispenser_account=algorand.account.localnet_dispenser(),
        min_spending_balance=AlgoAmount(amount={"algos": 2}),
    )

    app_factory = algorand.client.get_typed_app_factory(
        typed_factory=HelloWorldFactory,
        app_name="hello-world",
        default_sender=deployer.address,
        default_signer=deployer.signer,
        version="1.0",
        compilation_params=AppClientCompilationParams(
            updatable=False,
            deletable=False,
        ),
    )
    app_client, deploy_result = app_factory.deploy(
        on_update=OnUpdate.ReplaceApp,
        on_schema_break=OnSchemaBreak.Fail,
    )

    return app_client


def test_says_hello(hello_world_client: HelloWorldClient) -> None:
    result = hello_world_client.send.hello(args=("World",))

    assert result.abi_return == "Hello, World"


def test_simulate_says_hello_with_correct_budget_consumed(
    hello_world_client: HelloWorldClient,
) -> None:
    result = (
        hello_world_client.new_group()
        .hello(args=("World",))
        .hello(args=("Jane",))
        .simulate()
    )

    assert result.returns[0].value == "Hello, World"
    assert result.returns[1].value == "Hello, Jane"
    assert result.simulate_response["txn-groups"][0]["app-budget-consumed"] < 100

from typing import Callable

import pytest
from algokit_utils import (
    EnsureBalanceParameters,
    TransactionParameters,
    ensure_funded,
    get_localnet_default_account,
)
from algokit_utils.beta.account_manager import AddressAndSigner
from algokit_utils.beta.algorand_client import AlgorandClient
from algokit_utils.beta.client_manager import AlgoSdkClients
from algokit_utils.beta.composer import PayParams
from algosdk.atomic_transaction_composer import TransactionWithSigner
from algosdk.util import algos_to_microalgos
from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.indexer import IndexerClient

from smart_contracts.artifacts.voting.voting_client import VotingClient


@pytest.fixture(scope="session")
def algorand_client(
    algod_client: AlgodClient, indexer_client: IndexerClient
) -> AlgorandClient:
    algorand = AlgorandClient.from_clients(AlgoSdkClients(algod_client, indexer_client))
    algorand.set_suggested_params_timeout(0)

    return algorand


@pytest.fixture(scope="session")
def voting_client(algorand_client: AlgorandClient) -> VotingClient:
    client = VotingClient(
        algod_client=algorand_client.client.algod,
        creator=get_localnet_default_account(algorand_client.client.algod),
        indexer_client=algorand_client.client.indexer,
    )

    client.create_bare()
    ensure_funded(
        algorand_client.client.algod,
        EnsureBalanceParameters(
            account_to_fund=client.app_address, min_spending_balance_micro_algos=0
        ),
    )

    return client


@pytest.fixture(scope="session")
def voter_factory(algorand_client: AlgorandClient) -> Callable[[], AddressAndSigner]:
    def create_voter() -> AddressAndSigner:
        acct = algorand_client.account.random()
        ensure_funded(
            algorand_client.client.algod,
            EnsureBalanceParameters(
                account_to_fund=acct.address,
                min_spending_balance_micro_algos=algos_to_microalgos(10),
            ),
        )
        return acct

    return create_voter


def test_set_topic(voting_client: VotingClient) -> None:
    topic: str = "Hello, World"
    voting_client.set_topic(topic=topic)

    assert voting_client.get_global_state().topic.as_str == topic


def test_voting(
    algorand_client: AlgorandClient,
    voting_client: VotingClient,
    voter_factory: Callable[[], AddressAndSigner],
) -> None:
    for _ in range(3):
        voter = voter_factory()
        voter_client = VotingClient(
            algorand_client.client.algod,
            sender=voter.address,
            signer=voter.signer,
            app_id=voting_client.app_id,
        )
        voter_client.opt_in_opt_in()
        voted = voter_client.vote(
            pay=TransactionWithSigner(
                txn=algorand_client.transactions.payment(
                    PayParams(
                        sender=voter.address,
                        receiver=voting_client.app_address,
                        amount=10_000,
                    )
                ),
                signer=voter.signer,
            ),
            transaction_parameters=TransactionParameters(
                signer=voter.signer,
                sender=voter.address,
            ),
        )
        assert voted.return_value is True

    vote_count = voting_client.get_global_state().votes
    assert vote_count == 3

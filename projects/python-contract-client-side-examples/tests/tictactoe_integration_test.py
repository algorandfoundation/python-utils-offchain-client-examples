import base64

import algosdk.abi
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

from smart_contracts.artifacts.tictactoe.tic_tac_toe_client import TicTacToeClient


@pytest.fixture(scope="session")
def algorand_client(
    algod_client: AlgodClient, indexer_client: IndexerClient
) -> AlgorandClient:
    """Get an AlgorandClient to use throughout the tests"""
    algorand = AlgorandClient.from_clients(AlgoSdkClients(algod_client, indexer_client))
    algorand.set_suggested_params_timeout(0)

    return algorand


@pytest.fixture(scope="session")
def tictactoe_client(algorand_client: AlgorandClient) -> TicTacToeClient:
    """Get a TicTacToeClient to use throughout the tests"""
    client = TicTacToeClient(
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
def host(algorand_client: AlgorandClient) -> AddressAndSigner:
    """Get a host account to use throughout the tests"""
    acct = algorand_client.account.random()
    ensure_funded(
        algorand_client.client.algod,
        EnsureBalanceParameters(
            account_to_fund=acct.address,
            min_spending_balance_micro_algos=algos_to_microalgos(10),
        ),
    )

    return acct


@pytest.fixture(scope="session")
def guest(algorand_client: AlgorandClient) -> AddressAndSigner:
    """Get a host account to use throughout the tests"""
    acct = algorand_client.account.random()
    ensure_funded(
        algorand_client.client.algod,
        EnsureBalanceParameters(
            account_to_fund=acct.address,
            min_spending_balance_micro_algos=algos_to_microalgos(10),
        ),
    )

    return acct


@pytest.fixture(scope="session")
def game_id(
    tictactoe_client: TicTacToeClient,
    algorand_client: AlgorandClient,
    host: AddressAndSigner,
) -> int:
    last_game_id = tictactoe_client.get_global_state().id_counter

    result = tictactoe_client.opt_in_new_game(
        mbr=TransactionWithSigner(
            txn=algorand_client.transactions.payment(
                PayParams(
                    sender=host.address,
                    receiver=tictactoe_client.app_address,
                    amount=2_500 + 400 * (5 + 8 + 75),
                )
            ),
            signer=host.signer,
        ),
        transaction_parameters=TransactionParameters(
            signer=host.signer,
            sender=host.address,
            boxes=[(0, b"games" + (last_game_id + 1).to_bytes(8, "big"))],
        ),
    )

    return result.return_value


def test_join(
    tictactoe_client: TicTacToeClient,
    guest: AddressAndSigner,
    game_id: int,
):
    tictactoe_client.opt_in_join(
        game_id=game_id,
        transaction_parameters=TransactionParameters(
            signer=guest.signer,
            sender=guest.address,
            boxes=[(0, b"games" + game_id.to_bytes(8, "big"))],
        ),
    )


def test_moves(
    tictactoe_client: TicTacToeClient,
    algorand_client: AlgorandClient,
    host: AddressAndSigner,
    guest: AddressAndSigner,
    game_id: int,
):
    moves = [
        ((0, 0), (2, 2)),
        ((1, 1), (2, 1)),
        ((0, 2), (2, 0)),
    ]
    for host_move, guest_move in moves:
        tictactoe_client.move(
            game_id=game_id,
            x=host_move[0],
            y=host_move[1],
            transaction_parameters=TransactionParameters(
                signer=host.signer,
                sender=host.address,
                boxes=[(0, b"games" + game_id.to_bytes(8, "big"))],
                accounts=[guest.address],
            ),
        )

        tictactoe_client.move(
            game_id=game_id,
            x=guest_move[0],
            y=guest_move[1],
            transaction_parameters=TransactionParameters(
                signer=guest.signer,
                sender=guest.address,
                boxes=[(0, b"games" + game_id.to_bytes(8, "big"))],
                accounts=[host.address],
            ),
        )

    game_state = algosdk.abi.TupleType(
        [
            algosdk.abi.ArrayStaticType(algosdk.abi.ByteType(), 9),
            algosdk.abi.AddressType(),
            algosdk.abi.AddressType(),
            algosdk.abi.BoolType(),
            algosdk.abi.UintType(8),
        ]
    ).decode(
        base64.b64decode(
            algorand_client.client.algod.application_box_by_name(
                tictactoe_client.app_id, box_name=b"games" + game_id.to_bytes(8, "big")
            )["value"]
        )
    )
    assert game_state[3]

    assert tictactoe_client.get_local_state(host.address).games_played == 1
    assert tictactoe_client.get_local_state(guest.address).games_played == 1

    assert tictactoe_client.get_local_state(host.address).games_won == 0
    assert tictactoe_client.get_local_state(guest.address).games_won == 1

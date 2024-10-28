import algopy
from algopy import String, arc4


class Voting(algopy.ARC4Contract):
    def __init__(self) -> None:
        self.topic = algopy.GlobalState(
            algopy.Bytes(b"default_topic"), key="topic", description="Voting topic"
        )
        self.votes = algopy.GlobalState(
            algopy.UInt64(0),
            key="votes",
            description="Votes for the option",
        )
        self.voted = algopy.LocalState(
            algopy.UInt64, key="voted", description="Tracks if an account has voted"
        )

    @arc4.abimethod
    def set_topic(self, topic: String) -> None:
        self.topic.value = topic.bytes

    @arc4.abimethod
    def vote(self, pay: algopy.gtxn.PaymentTransaction) -> arc4.Bool:
        assert algopy.op.Global.group_size == algopy.UInt64(
            2
        ), "Expected 2 transactions"
        assert pay.amount == algopy.UInt64(10_000), "Incorrect payment amount"
        assert (
            pay.sender == algopy.Txn.sender
        ), "Payment sender must match transaction sender"

        _value, exists = self.voted.maybe(algopy.Txn.sender)
        if exists:
            return arc4.Bool(False)  # Already voted
        self.votes.value += algopy.UInt64(1)
        self.voted[algopy.Txn.sender] = algopy.UInt64(1)
        return arc4.Bool(True)

    @arc4.abimethod(readonly=True)
    def get_votes(self) -> arc4.UInt64:
        return arc4.UInt64(self.votes.value)

    @arc4.abimethod(allow_actions=["OptIn"])
    def opt_in(self) -> None:
        pass

    def clear_state_program(self) -> bool:
        return True

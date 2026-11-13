# The agreement rule behind a shared dollar rate: who a pending change still waits for, and what each
# party may do about it.
#
# Two things carry a dollar rate several people depend on — a pot, whose rate prices every owner's
# share, and a group, whose rate decides how much of one currency's debt a payment in another clears —
# and both change it the same way: one party proposes, every other party agrees, nothing changes until
# all of them have, and the proposer may withdraw it meanwhile. Who the parties ARE differs (a pot's
# owners, a group's members), so each caller resolves its own set of `agreers` and hands it here; the
# rule on top of that set is one rule, stated once.
#
# Pure: seat ids in, answers out. The callers own the reads, the lock and the writes.


# The parties a pending change still waits for.
def waiting_on(agreers: set[int], agreed: set[int]) -> set[int]:
    return agreers - agreed


# Whether every party it waits for has agreed, so the change applies now.
def is_agreed(agreers: set[int], agreed: set[int]) -> bool:
    return agreers <= agreed


# Whether a seat may agree to the pending change: a party it waits for who has not agreed yet — or, once
# nobody is left to wait for, any party, so a change whose last holdout went away can still be applied
# by somebody who is still here rather than staying pending for good.
def may_agree(member_id: int, agreers: set[int], agreed: set[int]) -> bool:
    return member_id in agreers and (member_id not in agreed or is_agreed(agreers, agreed))


# Whether a seat may withdraw the pending change: its proposer — or, once the proposer can no longer act
# (they left, or their seat lost its account), any party it waits for, so a stale proposal cannot block
# the rate for good.
def may_withdraw(member_id: int, proposed_by: int | None, agreers: set[int], *, proposer_can_act: bool) -> bool:
    if member_id == proposed_by:
        return True
    return not proposer_can_act and member_id in agreers

"""Integer offer shares. Pinned shares stay put, the rest split the remainder to 100."""


from app.errors import WeightError


def rebalance(offers: list) -> None:
    for offer in offers:
        if offer.status != "active":
            offer.share = 0

    active = [offer for offer in offers if offer.status == "active"]
    pinned = [offer for offer in active if offer.pinned]
    free = [offer for offer in active if not offer.pinned]

    for offer in pinned:
        if offer.pinned_share is None:
            offer.pinned_share = offer.share
        offer.share = int(offer.pinned_share)

    pinned_sum = sum(offer.share for offer in pinned)
    if pinned_sum > 100:
        raise WeightError(
            f"Сумма запиненных долей {pinned_sum}% больше 100. Сними пин или уменьши долю."
        )
    if not free:
        if active and pinned_sum != 100:
            raise WeightError(
                f"Запиненные доли дают {pinned_sum}%, а незапиненных офферов нет. Сними пин."
            )
        return
    if pinned_sum >= 100:
        raise WeightError(
            "Запиненные доли уже занимают 100%. Сними пин, чтобы добавить оффер."
        )

    remainder = 100 - pinned_sum
    ordered = sorted(free, key=lambda offer: (offer.offer_id, offer.id or 0))
    base, extra = divmod(remainder, len(ordered))
    if base == 0:
        raise WeightError(
            "На незапиненные офферы не хватает целого процента. Сними пин."
        )
    for index, offer in enumerate(ordered):
        offer.share = base + (1 if index < extra else 0)

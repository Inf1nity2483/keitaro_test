import re
import secrets
import string

ISO2 = frozenset(
    """
    AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ
    BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ
    CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ
    DE DJ DK DM DO DZ
    EC EE EG EH ER ES ET
    FI FJ FK FM FO FR
    GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY
    HK HM HN HR HT HU
    ID IE IL IM IN IO IQ IR IS IT
    JE JM JO JP
    KE KG KH KI KM KN KP KR KW KY KZ
    LA LB LC LI LK LR LS LT LU LV LY
    MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ
    NA NC NE NF NG NI NL NO NP NR NU NZ
    OM
    PA PE PF PG PH PK PL PM PN PR PS PT PW PY
    QA
    RE RO RS RU RW
    SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ
    TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ
    UA UG UM US UY UZ
    VA VC VE VG VI VN VU
    WF WS
    YE YT
    ZA ZM ZW
    """.split()
)


def parse_geos(raw: str) -> list[str]:
    parts = [part for part in re.split(r"[,;\s]+", raw.strip().upper()) if part]
    if not parts:
        raise ValueError("Укажи хотя бы один гео-код, например AU или MX,AU,RO")
    unknown = []
    for part in parts:
        if part == "UK":
            unknown.append("UK (для Великобритании нужен GB)")
        elif part not in ISO2:
            unknown.append(part)
    if unknown:
        raise ValueError("Неизвестные гео-коды: " + ", ".join(unknown))
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if part not in seen:
            seen.add(part)
            result.append(part)
    return result


def make_alias(length: int = 8) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def with_prefix(name: str, prefix: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise ValueError("Укажи имя кампании")
    if not prefix.startswith("test_") or prefix in {"test_", "test_фамилия_"}:
        raise ValueError(
            "В .env нужен CAMPAIGN_PREFIX вида test_фамилия_, например test_ivanov_"
        )
    if cleaned.startswith(prefix):
        final = cleaned
    else:
        final = f"{prefix}{cleaned}"
    if final == prefix:
        raise ValueError("Добавь имя после префикса")
    return final

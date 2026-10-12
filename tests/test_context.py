"""Wikipedia context layer: parsing only. Fixture wikitext is hand-written in the sites' formats."""

from __future__ import annotations

import datetime as dt

from trikal_pipeline.sources.wiki_context import day_title, parse_day, parse_year

DAY = """{{Current events|year=2020|month=03|day=23|content=
<!-- All news items below this line -->
;Business and economy
*[[Economic impact of the COVID-19 pandemic]]
**[[Fast food restaurant]] chain [[McDonald's]] closes all of its restaurants in the [[United Kingdom]]. [https://example.org/a (''The Guardian'')]
*A [[stock market]] index falls sharply.<ref>{{cite web|url=x}}</ref> [https://example.org/b (Reuters)]
;Sports
*A match is played without a source link.
}}"""

YEAR = """== Events ==
=== May ===
* [[May 11]]
** [[Pokhran-II]]: India conducts three underground nuclear tests in [[Pokhran]].
** The first coins are minted somewhere.
* [[May 13]]–[[May 14|14]] – Riots break out in a city, lasting two days.
== Births ==
* [[May 12]] – A person who must not appear, born.
"""

INDIA = """==Events==
=== May - August ===
* 11 May – India conducts 3 underground nuclear tests in [[Pokhran]].<ref>{{cite web|url=y}}</ref>
* 13 May – India carries out 2 more nuclear tests at [[Pokhran]].
==Births==
* 14 May – An actress, born.
"""


def test_daily_page_items_carry_category_story_and_original_outlet():
    items = parse_day(DAY)
    assert [i["text"] for i in items] == [
        "Fast food restaurant chain McDonald's closes all of its restaurants in the United Kingdom.",
        "A stock market index falls sharply.",
    ]
    assert items[0]["category"] == "Business and economy"
    assert items[0]["story"] == "Economic impact of the COVID-19 pandemic"
    assert (items[0]["source_name"], items[1]["source_name"]) == ("The Guardian", "Reuters")


def test_year_article_reads_events_only_with_dates_and_ranges():
    items = parse_year(YEAR, 1998)
    assert [(i["day"], i["text"][:20]) for i in items] == [
        (dt.date(1998, 5, 11), "Pokhran-II: India co"),
        (dt.date(1998, 5, 11), "The first coins are "),
        (dt.date(1998, 5, 13), "Riots break out in a"),
    ]


def test_in_india_article_uses_day_month_dates_and_skips_births():
    items = parse_year(INDIA, 1998)
    assert [i["day"] for i in items] == [dt.date(1998, 5, 11), dt.date(1998, 5, 13)]
    assert "<ref" not in items[0]["text"] and items[0]["text"].endswith("Pokhran.")


def test_daily_page_title():
    assert day_title(dt.date(2008, 10, 24)) == "Portal:Current_events/2008_October_24"

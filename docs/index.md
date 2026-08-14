# I Found a 28% Discrepancy in Child Mortality Data. Most of It Was My Own Mistake.

If you want to know how many Nigerian children died before their fifth birthday in 2003, there are two authoritative answers.

The World Health Organization says 157 per 1,000 live births. The Demographic and Health Surveys programme says 201.

That is 44 more deaths per 1,000 — a 28% gap between two of the most widely cited sources in global health. I built a pipeline to compare them systematically across six African countries and found the same pattern almost everywhere: DHS reads higher than WHO, in 36 of 45 matched observations, by an average of 8.6%.

Then I checked how I had matched them, and most of the gap disappeared.

What was left is smaller, stranger, and more interesting than what I started with.

---

## The two sources measure differently

**The DHS Program** runs household surveys. Interviewers ask women to recount their complete birth histories — every child born, and whether each is still living. Under-five mortality is calculated directly from those accounts. It is a measurement of a sample, in one country, at one time.

**The WHO Global Health Observatory** publishes modelled estimates. WHO assembles surveys, civil registration and census data from all available sources, then fits a statistical model producing a value for every country and every year — including years when nothing was measured.

One is a measurement. The other is an estimate. Comparing them is comparing a photograph to a painting of the same scene, and the interesting question is where the painting departs from the photograph.

---

## The mistake

I matched records on year. WHO's estimate for 2003 is an estimate *for 2003*. So I compared it against the DHS figure labelled 2003.

But that DHS figure does not describe 2003. It describes the **five years preceding the survey** — roughly 1998 to 2003, centred near 2000.

Under-five mortality was falling steadily throughout this period. A backward-looking five-year window therefore captures a higher-mortality era than the survey year itself. I was not comparing two estimates of the same thing. I was comparing 2003 against an average of 1998–2003, in a period when the number was dropping.

**Of course DHS read higher. I had built the gap into the comparison.**

---

## The correction

Two ways to fix it. Shift each DHS observation back to the midpoint of its window, or compare it against WHO averaged over the same five years. The second is more faithful, since it compares like periods rather than guessing a centre point.

Shifting first, to see how sensitive the result is:

| Match | Mean gap | DHS higher |
|---|---|---|
| Same year (original) | +8.6% | 36/45 |
| Shift 1 year | +4.9% | 28/45 |
| Shift 2 years | +1.4% | 26/45 |
| Shift 3 years | −2.0% | 17/45 |
| Shift 4 years | −5.3% | 11/45 |

The gap passes through zero at roughly a two-and-a-half-year shift — exactly the midpoint of a five-year window. That is what you would expect if the entire discrepancy were an artefact of misalignment.

The window-average method gives the same answer:

| | Naive match | Corrected |
|---|---|---|
| Mean gap | +8.6% | **+1.2%** |
| DHS higher in | 36/45 | 26/45 |

**Corrected, the two sources agree to within about 1%,** and DHS reads higher barely more often than chance would predict.

That is a reassuring finding about the quality of global health statistics. It is also the opposite of what I originally wrote down.

---

## What survived

Splitting by era is where it gets interesting:

| Era | Pairs | Naive gap | **Corrected gap** |
|---|---|---|---|
| Pre-2000 | 14 | +3.0% | **−1.3%** |
| **2000s** | **12** | **+19.5%** | **+7.1%** |
| 2010 onward | 19 | +5.7% | **−0.8%** |

The correction reduced the 2000s gap by roughly two-thirds. But it did not remove it — and it flattened the other two eras to approximately zero.

Before correcting, the 2000s looked like the worst case of a general problem. After correcting, it is the **only** case. Everywhere else the sources agree.

The individual outliers persist:

| Country | Survey | DHS | WHO (5-yr avg) | Gap |
|---|---|---|---|---|
| Kenya | 2003 | 115.0 | 90.3 | **+27%** |
| Nigeria | 2003 | 201.0 | 170.5 | **+18%** |
| Senegal | 2005 | 121.0 | 104.4 | **+16%** |
| Ghana | 2003 | 111.0 | 96.0 | **+16%** |

Four countries, three of them in the same year, all disagreeing in the same direction by a similar magnitude, after the obvious artefact has been removed.

---

## What might explain it

I can offer plausible mechanisms, not a demonstrated cause. With twelve observations in the affected decade, this is a hypothesis worth testing rather than a conclusion.

**Model smoothing against sparse data.** WHO fits a curve across available evidence. Curves pull outliers toward the trend — deliberately, since single surveys carry sampling error. In the 2000s, several of these countries had long gaps between surveys, so the model was interpolating across thin evidence. Where the model has less to anchor to, it leans harder on the regional trend, and a genuinely high survey result gets discounted.

**Revision asymmetry.** WHO reprocesses its entire historical series as new data arrives. Estimates from the 1990s have absorbed many rounds of revision informed by everything that came after. Recent years are close to their source data. The 2000s may sit in an awkward middle — old enough that the original data was thin, recent enough that revision has not fully worked through.

**A genuine measurement problem in that decade.** Less comfortable, and I cannot rule it out. If something about survey practice or recall accuracy differed systematically in the early 2000s, the surveys themselves could be the outlier rather than the model.

Distinguishing these requires WHO's uncertainty bounds and the DHS sampling errors, neither of which I have incorporated. That is the next piece of work, not this one.

---

## What I would take from this

**For anyone using these numbers:** the sources agree far better than a naive comparison suggests. If you find a large discrepancy, check your alignment before concluding anything about the data. Survey figures are windows, not points, and treating them as points manufactures disagreement.

**For the 2000s specifically:** the choice of source materially affects the answer in a way it does not for other periods. Anything evaluating a programme from that decade should state which source it used and why.

**Never mix sources within one series.** A chart using DHS for survey years and WHO for the gaps will show swings that are pure methodology. This is common in donor reporting and it is always wrong.

---

## Method

Both sources expose open APIs requiring no authentication:

- WHO Global Health Observatory OData API — `ghoapi.azureedge.net/api`
- The DHS Program API — `api.dhsprogram.com/rest/dhs`

Countries: Nigeria, Ghana, Kenya, Senegal, Egypt, South Africa. The pipeline fetches both sources, stores raw responses unmodified in dated folders, loads them into DuckDB, and applies documented filters. Six automated quality checks run on every build. It executes weekly on GitHub Actions.

Three filtering decisions materially affect the output, and all three were discovered by querying the data rather than anticipated:

1. **WHO sex dimension.** Four values exist, including nulls. Maternal mortality, immunisation coverage and health expenditure are not sex-disaggregated, so filtering on "both sexes" alone silently drops 534 rows.

2. **WHO wealth quintile.** Under-five mortality is additionally split into five wealth bands plus a national total — six rows per country-year. Without filtering to the total, every aggregate mixes a breakdown with the figure it decomposes. This one was invisible until the row counts stopped making sense.

3. **DHS recall period.** Up to five windows exist per indicator. Selected on coverage first: two- and three-year windows span all 43 surveys from 1986 to 2024, while five-year was discontinued after 2019. For under-five mortality I used the five-year window, the DHS convention for headline childhood mortality — which is precisely what made the alignment correction necessary.

---

## Limitations

- **Six countries, 45 paired observations, 12 in the affected decade.** Enough to identify a pattern, not to generalise.
- **Neither source's uncertainty is incorporated.** DHS sampling errors are not exposed by the API; WHO's confidence bounds are available but unused. Many of the remaining gaps may fall within overlapping intervals, which would make even the 2000s finding less striking.
- **The window-average correction assumes uniform weighting** across the five years. DHS's actual calculation weights by exposure, which is not quite the same.
- **South Africa contributes two observations,** so country-level conclusions about it mean nothing.
- **The mechanisms proposed above are untested.**

---

## Reproducing this

The pipeline is public: `github.com/saeeda-tech/naija-health-pipeline`

```bash
git clone https://github.com/saeeda-tech/naija-health-pipeline
cd naija-health-pipeline
pip install -r requirements.txt
python ingest.py && python load.py && python transform.py
```

No API keys, no manual downloads. It fetches everything from the two APIs and rebuilds from scratch.

---

## A closing note on method

I nearly published the first version. It had a confident headline, a clean table, and a plausible explanation. It was also mostly wrong, and anyone who knew how DHS recall windows work would have seen it immediately.

The correction cost about an hour and removed 86% of my finding. What remained was smaller but real, and I can now defend it.

That trade seems worth making every time.

---

*Data: WHO Global Health Observatory and The DHS Program. This analysis is independent and not affiliated with or endorsed by either organisation.*

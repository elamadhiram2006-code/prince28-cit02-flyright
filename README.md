
# FlyRight

[![CI](https://github.com/elamadhiram2006-code/prince28-cit02-flyright/actions/workflows/ci.yml/badge.svg)](https://github.com/elamadhiram2006-code/prince28-cit02-flyright/actions/workflows/ci.yml)

[![Live](https://img.shields.io/website?url=https%3A%2F%2Fflyright-api.onrender.com%2Fhealth&label=live)](https://flyright-api.onrender.com/docs)

[![Uptime (30 days)](https://img.shields.io/uptimerobot/ratio/m804769583-7423807f86e22a431fb4b8f5)](https://flyright-api.onrender.com/health)

Explains air passenger rights in India (cancellation, delay, denied boarding, baggage, assistance) and what compensation applies, citing DGCA rules.

**Status:** Day 1 foundation (FastAPI skeleton, quality gates). Live URL from Day 5.

## Who it's for

Software engineer who flies Chennai-Delhi monthly and whose flight was cancelled at the airport.

## The problem

Compensation depends on notice period, flight time, alternate flight and the cause. Airline terms and DGCA rules differ, and DGCA rules override airline terms.

## Data sources

DGCA Civil Aviation Requirements on passenger facilitation (Section 3, Series M, Part IV), CAR on persons with reduced mobility, baggage rules, airline conditions of carriage.

- https://www.dgca.gov.in/
- https://www.civilaviation.gov.in/
- https://airsewa.gov.in/
- Terms: Public regulations. Cite CAR section and revision date.

## Hardest problem (my interview story)

Rules engine over regulations: compensation depends on notice period, flight duration bands and alternate-flight timing, and the CAR overrides airline terms. The result must come from rules in code with the clause cited.

## Signature feature

Compensation checker: enter what happened and see what the airline owes you, with the CAR clause.

## Target metric

Entitlement correct for 95%+ of 40 test scenarios.

## Run it locally

### Using Docker Compose (recommended)

```bash
docker compose up --build -d
```

### Using uv

```bash
uv sync
cp .env.example .env
# Windows: copy .env.example .env
uv run uvicorn flyright.api.main:create_app --factory --reload
```

Then open http://localhost:8000/docs

## Checks

```bash
uv run pytest
uv run ruff check .
```

"""
api/schemas.py: the shape of every response the API sends back.

FastAPI uses these classes to (1) check our output has the right fields and
types, and (2) write the interactive docs at /docs automatically. A client
reading the docs knows exactly what each field is before writing any code.
"""

from datetime import date

from pydantic import BaseModel, Field


class Status(BaseModel):
    status: str = Field(examples=["ok"])
    data_source: str = Field(examples=["Supabase Postgres"])
    scored_month: date | None = Field(description="Month the latest scores describe")


class AccountRisk(BaseModel):
    """One account's current risk, as shown on the dashboard's Risk List."""

    account_id: str = Field(examples=["ACC-01314"])
    account_name: str
    segment: str = Field(examples=["Mid-Market"])
    region: str
    csm_name: str | None
    arr: float = Field(description="Annual recurring revenue, in dollars")
    churn_probability: float = Field(ge=0, le=1, description="Model's chance this account churns at renewal")
    risk_tier: str = Field(examples=["High", "Medium", "Low"])
    arr_at_risk: float = Field(description="churn_probability x arr")
    health_score: float = Field(ge=0, le=100, description="Rule-based score, 100 = healthiest")
    health_tier: str = Field(examples=["Healthy", "Watch", "At risk"])
    months_to_renewal: int
    reasons: list[str] = Field(description="Top reasons behind the health score, worst first")


class AccountList(BaseModel):
    total: int = Field(description="Accounts matching the filters, before limit/offset")
    limit: int
    offset: int
    accounts: list[AccountRisk]


class Contract(BaseModel):
    contract_id: str
    product_id: str
    start_date: date
    end_date: date
    seats: int
    arr: float


class HealthComponents(BaseModel):
    """The four parts of the health score, each 0-100. The weights are in brackets."""

    usage_trend: float = Field(description="Is usage rising or falling? (35%)")
    utilization: float = Field(description="Share of paid seats actually used (25%)")
    support: float = Field(description="Ticket load, SLA breaches and CSAT (25%)")
    contract: float = Field(description="Contract history, e.g. cut seats last renewal (15%)")


class AccountDetail(AccountRisk):
    industry: str
    employee_band: str
    parent_account_id: str | None
    ultimate_parent_account_id: str
    first_contract_date: date
    scored_month: date
    model_version: str
    health_components: HealthComponents
    current_contract: Contract | None


class HistoryPoint(BaseModel):
    month_start: date
    arr: float
    seat_utilization: float | None
    tickets: int | None
    health_score: float
    churn_probability: float
    risk_tier: str


class AccountHistory(BaseModel):
    account_id: str
    history: list[HistoryPoint]


class SegmentRetention(BaseModel):
    segment: str = Field(examples=["All", "SMB", "Mid-Market", "Enterprise"])
    month_start: date
    starting_customers: int
    retained_customers: int
    starting_arr: float
    ending_arr: float
    nrr: float = Field(description="12-month net revenue retention (1.0 = 100%)")
    grr: float = Field(description="12-month gross revenue retention, expansion excluded")


class Summary(BaseModel):
    as_of: date
    arr: float
    customers: int
    nrr: float
    grr: float
    arr_at_risk: float
    high_risk_accounts: int


class ModelInfo(BaseModel):
    best_model: str
    test_period: str
    test_contracts: int
    test_churn_rate: float
    results: dict[str, dict[str, float]] = Field(description="Test metrics for each model tried")
    feature_importance: dict[str, float]

# Length ceilings for the string parameters a router declares OUTSIDE a JSON body: path segments, query
# parameters and multipart form fields. A body field is capped on its schema; these are the same rule for
# the values FastAPI parses from the URL and the form, which no schema class carries.
#
# Each ceiling is the shape of what the parameter holds plus room, never a guess at what somebody types —
# and each is a cap rather than a membership check, so no request that succeeds today starts failing
# unless it was carrying a value no real one could be.

# An ISO 4217 code, the shape every currency the app stores or converts has. The display currency a page
# asks for comes from the user's settings, whose currency fields carry the same three-character cap.
CURRENCY_CODE_MAX_LENGTH = 3

# A key from a known set: a sort column (`payment_method` is the longest, at fourteen), a sort direction,
# a category or a payment method.
CODE_MAX_LENGTH = 32

# The longest column any list search matches against is a `notes` (500), and a search longer than the
# text it searches can match nothing.
SEARCH_MAX_LENGTH = 500

# `asset_prices.ticker` and `investments.ticker` are both VARCHAR(20).
TICKER_MAX_LENGTH = 20

# The import's column mapping, a JSON object of target field → source column. The widest spec has seven
# fields, so even at a generous 512-character header per field the honest mapping is under 4 KB; this is
# double that. Unbounded, one request carried 949 KB and 40,000 keys through `json.loads` before the
# service discarded all but seven.
IMPORT_MAPPING_MAX_LENGTH = 8192

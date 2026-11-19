"""Curated vocabularies used by the SRS analysis engine.

Every entry here is a transparent, reviewable rule input. Nothing is learned
or generated; changing a list changes the analysis in a predictable way.
"""

MODALS = {
    "shall not": ("prohibition", 3),
    "must not": ("prohibition", 3),
    "will not": ("prohibition", 2),
    "should not": ("discouraged", 1),
    "cannot": ("prohibition", 2),
    "can not": ("prohibition", 2),
    "may not": ("prohibition", 1),
    "shall": ("mandatory", 3),
    "must": ("mandatory", 3),
    "is required to": ("mandatory", 3),
    "are required to": ("mandatory", 3),
    "needs to": ("mandatory", 2),
    "need to": ("mandatory", 2),
    "has to": ("mandatory", 2),
    "have to": ("mandatory", 2),
    "will": ("declarative", 2),
    "should": ("recommended", 1),
    "may": ("optional", 0),
    "can": ("optional", 0),
    "could": ("optional", 0),
    "might": ("optional", 0),
}

SYSTEM_ACTORS = {
    "system", "application", "app", "software", "platform", "service", "server", "website",
    "web site", "portal", "module", "component", "api", "database", "backend", "frontend",
    "interface", "tool", "solution", "product", "engine", "scheduler", "gateway", "site",
    "mobile app", "web app", "dashboard", "subsystem",
}
HUMAN_ACTORS = {
    "user", "users", "admin", "admins", "administrator", "administrators", "customer", "customers",
    "client", "clients", "manager", "managers", "operator", "operators", "staff", "employee",
    "employees", "student", "students", "teacher", "teachers", "instructor", "doctor", "doctors",
    "patient", "patients", "guest", "guests", "visitor", "visitors", "member", "members", "buyer",
    "buyers", "seller", "sellers", "vendor", "vendors", "agent", "agents", "clerk", "reviewer",
    "reviewers", "owner", "owners", "approver", "auditor", "librarian", "cashier", "driver",
    "passenger", "author", "editor", "moderator", "tester", "developer", "supervisor", "officer",
    "applicant", "subscriber", "end user", "end users", "stakeholder", "accountant", "nurse",
}
PRONOUNS = {"it", "they", "them", "this", "that", "these", "those", "its", "their", "he", "she"}

# Verbs that commonly express requirement behaviour (base forms).
ACTION_VERBS = {
    "accept", "access", "add", "allow", "alert", "analyze", "analyse", "apply", "approve", "archive",
    "assign", "attach", "audit", "authenticate", "authorize", "authorise", "back", "backup", "block",
    "book", "browse", "build", "calculate", "cancel", "capture", "change", "charge", "check", "choose",
    "classify", "clear", "close", "collect", "compare", "compute", "configure", "confirm", "connect",
    "convert", "copy", "create", "deactivate", "debit", "decrypt", "define", "delete", "deliver", "deny",
    "deploy", "detect", "disable", "display", "download", "edit", "email", "enable", "encrypt", "enforce",
    "enroll", "enter", "escalate", "estimate", "evaluate", "execute", "expire", "export", "fetch", "filter",
    "find", "flag", "forward", "generate", "grant", "group", "handle", "hash", "hide", "highlight",
    "identify", "import", "include", "indicate", "inform", "initiate", "input", "insert", "install",
    "integrate", "invite", "issue", "keep", "launch", "limit", "link", "list", "load", "lock", "log",
    "login", "logout", "maintain", "manage", "mark", "mask", "merge", "migrate", "modify", "monitor",
    "move", "navigate", "notify", "open", "order", "pay", "permit", "persist", "place", "post", "predict",
    "prevent", "preview", "print", "prioritize", "process", "prompt", "protect", "provide", "publish",
    "purchase", "query", "queue", "rank", "rate", "read", "receive", "recommend", "record", "recover",
    "redirect", "refresh", "refund", "register", "reject", "remind", "remove", "rename", "render", "renew",
    "reopen", "replace", "reply", "report", "request", "require", "reserve", "reset", "resolve", "respond",
    "restore", "restrict", "resume", "retain", "retrieve", "retry", "return", "review", "revoke", "route",
    "run", "save", "scan", "schedule", "search", "select", "send", "set", "share", "show", "sign", "sort",
    "start", "stop", "store", "submit", "subscribe", "suggest", "support", "suspend", "switch", "sync",
    "synchronize", "synchronise", "terminate", "track", "transfer", "transmit", "trigger", "unlock",
    "unsubscribe", "update", "upgrade", "upload", "use", "validate", "verify", "view", "withdraw", "write",
    "approve", "comment", "like", "follow", "message", "chat", "invoice", "bill", "checkout", "ship",
    "dispatch", "allocate", "calculate", "pick", "scan", "measure", "count", "sum", "summarize",
    "summarise", "translate", "tag", "upvote", "vote", "answer", "ask", "attend", "grade", "evaluate",
}
IRREGULAR_PARTICIPLES = {
    "sent": "send", "shown": "show", "made": "make", "kept": "keep", "written": "write", "read": "read",
    "built": "build", "taken": "take", "given": "give", "held": "hold", "paid": "pay", "set": "set",
    "run": "run", "found": "find", "chosen": "choose", "known": "know", "seen": "see", "done": "do",
    "begun": "begin", "hidden": "hide", "brought": "bring", "bought": "buy", "sold": "sell",
    "told": "tell", "put": "put", "left": "leave", "met": "meet", "lost": "lose", "won": "win",
}
# Words that, after a modal, are adverbs/fillers rather than the main verb.
VERB_FILLERS = {"also", "only", "automatically", "securely", "immediately", "always", "never", "not",
                "be", "able", "to", "then", "still", "properly", "correctly", "successfully",
                "efficiently", "quickly", "easily", "periodically", "continuously", "manually"}

STATE_CHANGING = {"create", "add", "update", "edit", "modify", "delete", "remove", "submit", "register",
                  "pay", "purchase", "cancel", "approve", "reject", "transfer", "upload", "book",
                  "reserve", "place", "checkout", "refund", "assign", "change", "reset", "save", "store",
                  "archive", "restore", "enroll", "withdraw", "order", "publish", "post", "import",
                  "deactivate", "suspend", "lock", "unlock", "merge", "rename", "renew"}
DATA_ENTRY = {"register", "submit", "enter", "input", "create", "add", "update", "edit", "modify",
              "upload", "search", "filter", "login", "sign", "book", "reserve", "pay", "purchase",
              "checkout", "import", "post", "comment", "order", "enroll", "apply", "request"}
QUERY_ACTIONS = {"search", "view", "display", "show", "list", "browse", "generate", "export", "report",
                 "calculate", "compute", "retrieve", "fetch", "query", "download", "print", "preview",
                 "summarize", "summarise", "filter", "sort", "track", "find", "compare"}
EVENT_ACTIONS = {"notify", "send", "alert", "email", "remind", "escalate", "backup", "sync",
                 "synchronize", "synchronise", "expire", "lock", "archive", "purge", "trigger",
                 "schedule", "refresh", "renew", "log", "audit", "generate", "suspend"}
SENSITIVE_ACTIONS = {"delete", "remove", "approve", "reject", "refund", "transfer", "assign", "grant",
                     "revoke", "configure", "deactivate", "suspend", "manage", "export", "modify",
                     "override", "reset", "unlock", "publish", "withdraw", "edit", "update"}
RISKY_OPERATIONS = {"pay", "purchase", "checkout", "transfer", "refund", "upload", "import", "export",
                    "sync", "synchronize", "synchronise", "backup", "restore", "migrate", "send",
                    "transmit", "integrate", "charge", "debit", "process", "save", "store"}

SENSITIVE_DATA_TERMS = ["password", "credential", "credit card", "card number", "cvv", "payment",
                        "bank account", "personal data", "personal information", "pii", "health",
                        "medical", "aadhaar", "ssn", "social security", "date of birth", "salary",
                        "biometric", "otp", "token", "secret", "private key", "financial"]
SECURITY_CONTROLS = ["encrypt", "hash", "salt", "mask", "tls", "https", "ssl", "access control",
                     "role-based", "rbac", "permission", "authoriz", "authoris", "authenticat",
                     "multi-factor", "two-factor", "2fa", "mfa", "audit", "token", "session timeout",
                     "lockout", "lock the account", "captcha", "firewall", "sanitiz", "least privilege"]
AUTHORIZATION_TERMS = ["authorized", "authorised", "authenticated", "logged-in", "logged in", "signed in",
                       "role", "permission", "privilege", "only administrator", "only admin",
                       "administrators only", "admin only", "access control", "rbac", "owner of",
                       "own ", "their own", "with access", "approved user", "verified user",
                       "registered user", "registered users", "authorised user", "authorized user"]
ERROR_TERMS = ["error", "invalid", "fail", "failure", "failed", "exception", "reject", "rejected",
               "timeout", "time out", "times out", "unavailable", "not available", "retry", "otherwise",
               "incorrect", "wrong", "unsuccessful", "denied", "deny", "cannot be", "not found",
               "fallback", "warning", "if not", "unless"]
RECOVERY_TERMS = ["retry", "retries", "rollback", "roll back", "restore", "recover", "recovery",
                  "fallback", "resume", "compensat", "revert", "backup", "redundan", "failover",
                  "queue", "idempot", "not charged", "no partial"]
VALIDATION_TERMS = ["valid", "validate", "verify", "format", "required field", "mandatory", "length",
                    "characters", "range", "unique", "must contain", "must be a", "numeric", "digits",
                    "maximum", "minimum", "at least", "no more than", "allowed", "pattern", "regex",
                    "checksum", "file type", "file size", "between", "non-empty", "not empty", "@"]
OUTCOME_TERMS = ["display", "show", "return", "receive", "notify", "notification", "confirm",
                 "confirmation", "message", "redirect", "save", "saved", "store", "stored", "update",
                 "updated", "create", "created", "record", "recorded", "log", "logged", "send", "sent",
                 "generate", "generated", "status", "result", "response", "report", "email", "appear",
                 "visible", "available", "download", "export", "print", "list", "reject", "deny",
                 "prevent", "lock", "block", "mark", "set to", "changed to", "becomes", "so that",
                 "in order to", "receipt", "acknowledg"]
INPUT_TERMS = ["enter", "entering", "input", "form", "field", "fields", "parameter", "provide",
               "providing", "with their", "with his", "with her", "using their", "using his", "email",
               "password", "username", "name", "address", "phone", "date", "amount", "quantity",
               "file", "keyword", "query", "criteria", "following", "details", "information", ":"]
OUTPUT_TERMS = ["display", "show", "list", "table", "report", "return", "results", "summary",
                "chart", "graph", "file", "pdf", "csv", "excel", "format", "columns", "fields",
                "including", "containing", "with the", "sorted", "grouped", "total", "count"]
DEPENDENCY_TERMS = ["third-party", "third party", "external system", "external service", "external api",
                    "existing system", "legacy system", "gateway", "provider", "integration with",
                    "integrate with", "integrates with", "interface with", "connect to", "via the",
                    "erp", "crm", "sms service", "email service", "payment gateway", "partner system"]
TRIGGER_WORDS = ["when", "whenever", "if", "unless", "after", "before", "upon", "once", "until",
                 "while", "during", "in case", "as soon as", "on receipt", "on completion",
                 "on successful", "on failure", "each time", "every time", "at the end of",
                 "at the start of", "prior to", "following"]
SCHEDULE_PATTERN = (r"\b(every|each)\s+(\d+\s+)?(second|minute|hour|day|night|week|month|year)s?\b"
                    r"|\b(daily|hourly|weekly|monthly|yearly|annually|nightly)\b|\bat\s+\d{1,2}(:\d{2})?\s*(am|pm)?\b"
                    r"|\bat midnight\b|\bin real[- ]time\b|\bimmediately\b|\bwithin \d+")

# Subjective words: (term, why it is vague, what to specify).
VAGUE_TERMS = {
    "fast": ("speed is subjective", "a maximum response or processing time, the operation measured, and the load conditions"),
    "quick": ("speed is subjective", "a maximum completion time"),
    "quickly": ("speed is subjective", "a maximum completion time"),
    "rapid": ("speed is subjective", "a maximum completion time"),
    "slow": ("speed is subjective", "the acceptable time limit"),
    "responsive": ("responsiveness is subjective", "a response-time target, or the screen sizes it must adapt to"),
    "efficient": ("efficiency has no stated metric", "the resource or time metric and its threshold"),
    "efficiently": ("efficiency has no stated metric", "the resource or time metric and its threshold"),
    "user-friendly": ("usability is subjective", "a usability criterion such as task completion rate, steps, or time for a named user group"),
    "user friendly": ("usability is subjective", "a usability criterion such as task completion rate, steps, or time"),
    "easy": ("ease is subjective", "the user task and how successful completion is measured"),
    "easily": ("ease is subjective", "the user task and how successful completion is measured"),
    "simple": ("simplicity is subjective", "a measurable usability or complexity criterion"),
    "intuitive": ("intuitiveness is subjective", "a learnability measure, e.g. completion without training"),
    "secure": ("security is not a verifiable property by itself", "the concrete security controls and the assets they protect"),
    "securely": ("security is not a verifiable property by itself", "the concrete security controls (e.g. encryption, access control)"),
    "safe": ("safety is not defined", "the hazards and the required safeguards"),
    "reliable": ("reliability has no metric", "an availability, failure-rate, or recovery objective"),
    "robust": ("robustness has no metric", "the failure conditions and the required behavior"),
    "scalable": ("scalability has no metric", "the expected users, workload, data volume, and growth"),
    "flexible": ("flexibility is undefined", "which changes must be supported and how"),
    "modern": ("modern is subjective", "the specific standards or capabilities required"),
    "attractive": ("attractiveness is subjective", "the design guidelines or acceptance criteria"),
    "appropriate": ("'appropriate' leaves the rule undefined", "the explicit rule or condition"),
    "appropriately": ("'appropriately' leaves the rule undefined", "the explicit rule or condition"),
    "adequate": ("'adequate' leaves the level undefined", "the required level or threshold"),
    "sufficient": ("'sufficient' leaves the level undefined", "the required level or threshold"),
    "reasonable": ("'reasonable' leaves the limit undefined", "the explicit limit"),
    "normal": ("'normal' conditions are undefined", "the operating conditions"),
    "normally": ("'normally' hides the exception cases", "the exact conditions for each case"),
    "large": ("size is subjective", "the numeric size and unit"),
    "small": ("size is subjective", "the numeric size and unit"),
    "high": ("level is subjective", "the numeric level and unit"),
    "low": ("level is subjective", "the numeric level and unit"),
    "minimal": ("'minimal' has no value", "the maximum acceptable value"),
    "optimal": ("'optimal' has no value", "the target value or optimisation criterion"),
    "significant": ("'significant' has no value", "the numeric threshold"),
    "soon": ("timing is undefined", "a measurable time limit"),
    "timely": ("timing is undefined", "a measurable time limit"),
    "recent": ("time window is undefined", "the time window"),
    "regularly": ("frequency is undefined", "the frequency or schedule"),
    "periodically": ("frequency is undefined", "the frequency or schedule"),
    "frequently": ("frequency is undefined", "the frequency"),
    "seamless": ("seamlessness is subjective", "the integration behavior and failure handling"),
    "seamlessly": ("seamlessness is subjective", "the integration behavior and failure handling"),
    "best": ("superlatives are unverifiable", "a measurable target"),
    "state-of-the-art": ("the phrase is unverifiable", "the specific capability required"),
    "high performance": ("performance level is subjective", "throughput or latency targets"),
    "high availability": ("availability level is subjective", "an uptime percentage and measurement period"),
    "highly available": ("availability level is subjective", "an uptime percentage and measurement period"),
    "as fast as possible": ("open-ended speed requirement", "a maximum time"),
    "as soon as possible": ("open-ended timing", "a maximum time"),
    "as much as possible": ("open-ended goal", "a measurable target"),
    "if possible": ("makes the obligation optional and undefined", "whether this is required, and under which conditions"),
    "where possible": ("makes the obligation optional and undefined", "the conditions under which it applies"),
    "as appropriate": ("leaves the rule undefined", "the explicit rule"),
    "as required": ("leaves the rule undefined", "the explicit trigger or rule"),
    "as needed": ("leaves the trigger undefined", "the event or condition that triggers the behavior"),
    "when necessary": ("leaves the trigger undefined", "the event or condition that triggers the behavior"),
    "if necessary": ("leaves the trigger undefined", "the condition that triggers the behavior"),
    "some": ("quantity is undefined", "the exact items or quantity"),
    "several": ("quantity is undefined", "the exact quantity"),
    "many": ("quantity is undefined", "the exact quantity"),
    "various": ("the set is undefined", "the specific items"),
    "a lot of": ("quantity is undefined", "the exact quantity"),
    "few": ("quantity is undefined", "the exact quantity"),
    "user-centric": ("phrase is unverifiable", "measurable usability criteria"),
}
OPEN_ENDED = ["etc", "and so on", "and/or", "including but not limited to", "such as", "any other",
              "all relevant", "all necessary", "and more", "among others", "or similar", "and the like",
              "other related", "similar features"]
AMBIGUOUS_PHRASES = {
    "and/or": "It is unclear whether both options or only one are required.",
    "support": "'support' does not say what the system must do with the item.",
    "handle": "'handle' does not define the expected behavior.",
    "manage": "'manage' bundles several operations (create, view, update, delete) without saying which.",
    "process": "'process' does not define the processing steps or result.",
    "deal with": "'deal with' does not define the expected behavior.",
    "take care of": "'take care of' does not define the expected behavior.",
    "the above": "Refers to earlier text that may change position or meaning.",
    "as mentioned": "Relies on context outside the requirement.",
    "as described": "Relies on context outside the requirement unless a reference is given.",
    "same as": "Relies on another statement without identifying it.",
    "tbd": "The requirement still contains an unresolved placeholder.",
    "tbc": "The requirement still contains an unconfirmed placeholder.",
    "to be decided": "The requirement still contains an unresolved decision.",
    "to be determined": "The requirement still contains an unresolved decision.",
}
ABSOLUTE_TERMS = ["always", "never", "100%", "100 percent", "every time", "zero downtime", "no downtime",
                  "all the time", "without any", "completely", "fully secure", "unlimited", "infinite",
                  "instantly", "instantaneously", "any device", "all devices", "all browsers", "error-free",
                  "bug-free", "never fail", "no errors", "at all times"]
UNREALISTIC_PATTERNS = [
    (r"\b100\s*(%|percent)\s*(uptime|availability|available)", "100% availability is not achievable in practice; specify an SLA such as a percentage over a period."),
    (r"\bzero\s+(downtime|errors?|defects?|latency)\b", "Zero downtime/errors/latency cannot be verified or guaranteed."),
    (r"\bnever\s+(fail|crash|go down|be unavailable|lose)", "A guarantee that something never fails cannot be verified; specify a reliability target."),
    (r"\b(unlimited|infinite)\s+\w+", "Unlimited capacity cannot be built or tested; specify the supported maximum."),
    (r"\b(instantly|instantaneously|in no time)\b", "Instant response cannot be measured; specify a maximum time."),
    (r"\b(all|any)\s+(browsers?|devices?|platforms?|operating systems?)\b", "Supporting every browser/device is untestable; list supported platforms and versions."),
    (r"\b(fully|completely|100\s*%)\s+secure\b", "Absolute security cannot be verified; specify controls and threat assumptions."),
    (r"\b(bug|error)[- ]free\b", "Defect-free software cannot be verified; specify quality targets."),
]
DESIGN_TERMS = ["button", "dropdown", "drop-down", "checkbox", "radio button", "mysql", "mongodb",
                "postgresql", "oracle", "java", "python", "react", "angular", "spring", "node.js",
                "aws", "azure", "kubernetes", "docker", "tab ", "popup", "pop-up", "modal window",
                "rest api", "graphql", "microservice", "redis", "kafka", "sql server"]

NFR_METRIC_TERMS = {
    "Performance": r"\b\d+(\.\d+)?\s*(ms|milliseconds?|s|secs?|seconds?|minutes?|mins?)\b|\b\d+\s*(requests?|transactions?|tps|rps|queries)\s*(per|/)\s*(second|sec|minute|s)\b|\b\d+\s*(concurrent|simultaneous)\b|\bp9\d\b|\bpercentile\b",
    "Availability": r"\b\d+(\.\d+)?\s*(%|percent\b)|\b\d+\s*(minutes?|hours?)\s+(of\s+)?(downtime|per month|per year)",
    "Reliability": r"\bmtbf\b|\bmttr\b|\brpo\b|\brto\b|\b\d+(\.\d+)?\s*(%|percent\b)|\b\d+\s*(failures?|errors?)\b|\bwithin \d+",
    "Usability": r"\bwcag\b|\b\d+\s*(clicks?|steps?|seconds?|minutes?)\b|\b\d+\s*(%|percent)\s+of\s+users\b|\bsection 508\b",
    "Scalability": r"\b\d[\d,]*\s*(users?|requests?|transactions?|records?|tb|gb|concurrent)\b",
    "Compatibility": r"\b(chrome|firefox|safari|edge|android|ios|windows|macos|linux)\b",
    "Maintainability": r"\b\d+\s*(%|percent)\s+(test )?coverage\b|\bcyclomatic\b|\bwithin \d+\s*(hours?|days?)\b",
}

# Category name -> (keywords, weight). Weighted keyword evidence drives classification.
CATEGORY_RULES = {
    "Security": (["security", "secure", "encrypt", "password", "authentication", "authenticate",
                  "authorization", "authorize", "access control", "role-based", "multi-factor",
                  "two-factor", "mfa", "2fa", "audit log", "session", "token", "hash", "tls", "https",
                  "firewall", "vulnerab", "attack", "injection", "xss", "csrf", "lockout",
                  "unauthorized", "unauthorised", "permission", "credential", "otp", "captcha"], 1.0),
    "Performance": (["performance", "response time", "latency", "throughput", "load time", "loads within",
                     "concurrent", "requests per second", "transactions per second", "milliseconds",
                     "within \\d+ seconds", "fast", "speed", "quickly", "page load", "processing time"], 1.0),
    "Availability": (["availability", "available", "available 24", "24/7", "24x7", "uptime", "downtime", "service level",
                      "sla", "failover", "high availability", "highly available"], 1.0),
    "Reliability": (["reliability", "reliable", "failure rate", "fault toleran", "recover", "retry",
                     "data loss", "recovery point", "recovery time", "mtbf", "mttr", "rpo", "rto",
                     "redundan", "resilien", "crash"], 1.0),
    "Usability": (["usability", "user-friendly", "user friendly", "accessible", "accessibility", "easy to use",
                   "intuitive", "learnability", "screen reader", "wcag", "keyboard navigation", "help text",
                   "tooltip", "language", "localization", "localisation", "font size", "contrast"], 1.0),
    "Compatibility": (["compatible", "compatibility", "browser", "operating system", "cross-platform",
                       "android", "ios", "windows", "linux", "macos", "chrome", "firefox", "safari",
                       "mobile device", "tablet", "screen size", "responsive"], 1.0),
    "Maintainability": (["maintainab", "modular", "code quality", "coding standard", "documentation",
                         "extensib", "configurable", "logging", "monitoring", "diagnostic",
                         "upgrade", "deploy", "refactor", "test coverage"], 0.8),
    "Privacy": (["privacy", "personal data", "personal information", "sensitive data", "consent", "gdpr",
                 "data retention", "anonymi", "pseudonym", "right to be forgotten", "erase personal",
                 "data protection", "pii", "opt-out", "opt out", "cookie"], 1.0),
    "Data": (["database", "data", "record", "records", "field", "schema", "backup", "restore", "import",
              "export", "store", "stored", "retain", "retention", "archive", "csv", "format",
              "data integrity", "persist"], 0.6),
    "Interface / Integration": (["api", "interface", "integration", "integrate", "webhook", "json", "xml",
                                 "http", "endpoint", "third-party", "third party", "external system",
                                 "gateway", "rest", "soap", "protocol", "sms", "email service", "sync"], 0.9),
    "Regulatory / Compliance": (["compliance", "comply", "regulation", "regulatory", "standard", "iso ",
                                 "pci", "hipaa", "gdpr", "sox", "legal", "law", "audit trail", "rbi",
                                 "accessibility act", "certif"], 1.0),
    "Scalability": (["scalab", "scale", "number of users", "concurrent users", "growth", "peak load",
                     "horizontal", "elastic"], 1.0),
    "Business Rule": (["discount", "eligible", "eligibility", "policy", "fee", "penalty", "tax", "commission",
                       "only if", "provided that", "must not exceed", "cannot exceed", "limit of", "rule",
                       "approval", "threshold", "late fee", "interest rate", "refund policy"], 0.9),
    "Technical Constraint": (["shall use", "must use", "shall be developed", "must be developed",
                              "implemented in", "built using", "written in", "framework", "technology stack",
                              "hosted on", "deployed on", "must run on", "shall run on", "programming language",
                              "database platform", "budget", "open-source license"], 1.0),
}
NFR_CATEGORIES = {"Security", "Performance", "Availability", "Reliability", "Usability", "Compatibility",
                  "Maintainability", "Privacy", "Scalability", "Regulatory / Compliance"}

# Terminology groups: canonical term -> variants that usually mean the same thing in one SRS.
SYNONYM_GROUPS = {
    "user": ["user", "end user", "customer", "client", "member"],
    "administrator": ["administrator", "admin", "system administrator", "sysadmin"],
    "log in": ["log in", "login", "sign in", "signin", "log on", "logon"],
    "log out": ["log out", "logout", "sign out", "signout", "log off"],
    "register": ["register", "sign up", "signup", "create an account", "create account", "enrol", "enroll"],
    "delete": ["delete", "remove", "erase", "purge"],
    "update": ["update", "edit", "modify", "change"],
    "display": ["display", "show", "present"],
    "search": ["search", "look up", "lookup", "find"],
    "password reset": ["reset password", "password reset", "forgot password", "password recovery", "recover password"],
    "account": ["account", "user account", "user profile", "profile"],
    "order": ["order", "purchase order", "booking"],
    "product": ["product", "item", "article", "goods"],
    "notification": ["notification", "alert", "notice"],
    "report": ["report", "summary report", "statement"],
}

STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "by", "with", "from", "at", "is", "are",
    "be", "as", "it", "its", "this", "that", "these", "those", "shall", "must", "will", "should", "can",
    "may", "not", "all", "any", "each", "every", "able", "allow", "allowed", "system", "application",
    "user", "users", "which", "who", "their", "his", "her", "they", "them", "has", "have", "into", "within",
    "when", "if", "after", "before", "also", "only", "such", "via", "using", "use", "per", "than", "then",
    "so", "do", "does", "provide", "provides", "need", "needs", "required", "require", "requires",
}

REQUIREMENT_ID_PATTERN = (r"(?:[A-Z][A-Z0-9]{0,9}[-_ .]?\d+(?:[.\-]\d+)*|\d+(?:\.\d+){1,4})")

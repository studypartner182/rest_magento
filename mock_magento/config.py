from datetime import timedelta

API_PREFIX = "/rest/V1"

JWT_SECRET_KEY = "mock-magento-super-secret-key-change-me"
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE = timedelta(minutes=2)
REFRESH_TOKEN_EXPIRE = timedelta(minutes=10)

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "Admin@123"
ADMIN_ROLE = "Administrator"

DEFAULT_PAGE_SIZE = 10
DEFAULT_CURRENT_PAGE = 1
MAX_REQUESTS_PER_MINUTE = 20

import enum


class RoleEnum(str, enum.Enum):
    """User roles. Every user has at least USER. Extra roles are appended,
    e.g. a group leader has [USER, GROUP_LEADER]. Only one SUPER_ADMIN exists."""
    USER = "USER"
    GROUP_LEADER = "GROUP_LEADER"
    FINANCE = "FINANCE"
    ADMIN = "ADMIN"
    SUPER_ADMIN = "SUPER_ADMIN"


class MaritalStatus(str, enum.Enum):
    SINGLE = "SINGLE"
    MARRIED = "MARRIED"

class Group(str, enum.Enum):
    RUBY = "RUBY"
    LEVITE = "LEVITE"
    JUDAH = "JUDAH"
    SIMEON = "SIMEON"

class GroupMembershipStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
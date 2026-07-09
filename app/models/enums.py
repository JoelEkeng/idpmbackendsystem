import enum


class RoleEnum(str, enum.Enum):
    """User roles. Every user has the base USER role. Extra roles are appended,
    e.g. a regular member is [USER, MEMBER] and a group leader is
    [USER, GROUP_LEADER]. USER and ADMIN are distinct. Only one SUPER_ADMIN
    exists."""
    USER = "USER"
    MEMBER = "MEMBER"
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
import enum


class RoleEnum(str, enum.Enum):
    MEMBER = "MEMBER"
    GROUP_LEADER = "GROUP_LEADER"
    FINANCE = "FINANCE"
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
# Issue #4: Create User Dashboard Component with Tests (TDD)

**Type:** Feature
**Labels:** `feature`, `frontend`, `tdd`, `react`, `testing`
**Assignee:** ADWS Bot
**Status:** Open

## Description

Create a user dashboard component with comprehensive test coverage using Test-Driven Development (TDD). This component will display user information, activity feed, and quick actions.

## Requirements

### Test-Driven Development Approach
**IMPORTANT:** Generate comprehensive tests FIRST using React Testing Library, then implement the component to make tests pass.

### Component Specifications

**Component Name:** `UserDashboard`
**Location:** `app/client/src/components/UserDashboard.tsx`
**Test Location:** `app/client/src/components/__tests__/UserDashboard.test.tsx`

### Functional Requirements

1. **User Profile Section:**
   - Display user avatar (image or initials fallback)
   - Display user name
   - Display user email
   - Display member since date

2. **Activity Feed Section:**
   - Display list of recent activities (max 5)
   - Each activity shows:
     - Activity icon
     - Activity description
     - Timestamp (relative time: "2 hours ago")
   - Show "No recent activity" if empty

3. **Quick Actions Section:**
   - "Edit Profile" button
   - "View Settings" button
   - "Logout" button

4. **Component Props:**
```tsx
interface User {
  id: string;
  name: string;
  email: string;
  avatarUrl?: string;
  memberSince: Date;
}

interface Activity {
  id: string;
  type: 'login' | 'profile_update' | 'settings_change';
  description: string;
  timestamp: Date;
}

interface UserDashboardProps {
  user: User;
  activities: Activity[];
  onEditProfile?: () => void;
  onViewSettings?: () => void;
  onLogout?: () => void;
}
```

### Test Coverage Requirements

Generate comprehensive tests using React Testing Library for:

#### 1. **Rendering Tests**
```tsx
describe('UserDashboard Rendering', () => {
  test('renders user name correctly', () => {
    // Test that user name is displayed
  });

  test('renders user email correctly', () => {
    // Test that email is displayed
  });

  test('displays user avatar when avatarUrl is provided', () => {
    // Test avatar image rendering
  });

  test('displays initials fallback when avatarUrl is not provided', () => {
    // Test initials fallback (e.g., "JD" for "John Doe")
  });

  test('formats member since date correctly', () => {
    // Test date formatting
  });
});
```

#### 2. **Activity Feed Tests**
```tsx
describe('UserDashboard Activity Feed', () => {
  test('renders all activities when provided', () => {
    // Test that all activities render
  });

  test('limits activities to 5 most recent', () => {
    // Test with 10 activities, should show 5
  });

  test('shows "No recent activity" message when activities array is empty', () => {
    // Test empty state
  });

  test('displays relative timestamps for activities', () => {
    // Test timestamp formatting ("2 hours ago")
  });

  test('displays correct icon for each activity type', () => {
    // Test different activity type icons
  });
});
```

#### 3. **Quick Actions Tests**
```tsx
describe('UserDashboard Quick Actions', () => {
  test('calls onEditProfile when Edit Profile button is clicked', () => {
    // Test button click handler
  });

  test('calls onViewSettings when View Settings button is clicked', () => {
    // Test button click handler
  });

  test('calls onLogout when Logout button is clicked', () => {
    // Test button click handler
  });

  test('does not crash when callback props are undefined', () => {
    // Test graceful handling of missing callbacks
  });
});
```

#### 4. **Accessibility Tests**
```tsx
describe('UserDashboard Accessibility', () => {
  test('has proper heading hierarchy', () => {
    // Test h1, h2, h3 usage
  });

  test('all interactive elements are keyboard accessible', () => {
    // Test tab navigation
  });

  test('has proper ARIA labels for buttons', () => {
    // Test aria-label attributes
  });

  test('avatar has alt text', () => {
    // Test image alt attribute
  });
});
```

#### 5. **Edge Cases Tests**
```tsx
describe('UserDashboard Edge Cases', () => {
  test('handles very long user names gracefully', () => {
    // Test text truncation/wrapping
  });

  test('handles very long activity descriptions', () => {
    // Test description truncation
  });

  test('handles future dates in activities gracefully', () => {
    // Test edge case timestamps
  });
});
```

### Visual Layout

```
┌────────────────────────────────────────┐
│  User Dashboard                        │
├────────────────────────────────────────┤
│                                        │
│  ┌──────────────────────────────────┐  │
│  │  Profile                         │  │
│  │  ┌────┐                          │  │
│  │  │ JD │  John Doe                │  │
│  │  └────┘  john@example.com        │  │
│  │          Member since Jan 2024   │  │
│  └──────────────────────────────────┘  │
│                                        │
│  ┌──────────────────────────────────┐  │
│  │  Recent Activity                 │  │
│  │                                  │  │
│  │  🔐 Logged in - 2 hours ago      │  │
│  │  ✏️  Updated profile - 1 day ago  │  │
│  │  ⚙️  Changed settings - 2 days    │  │
│  │                                  │  │
│  └──────────────────────────────────┘  │
│                                        │
│  ┌──────────────────────────────────┐  │
│  │  Quick Actions                   │  │
│  │                                  │  │
│  │  [Edit Profile] [Settings] [🚪]  │  │
│  │                                  │  │
│  └──────────────────────────────────┘  │
│                                        │
└────────────────────────────────────────┘
```

### File Structure Expected
```
app/client/src/
├── components/
│   ├── UserDashboard.tsx              # Main component
│   ├── UserDashboard.module.css       # Component styles
│   ├── __tests__/
│   │   └── UserDashboard.test.tsx     # Comprehensive test suite
│   └── Avatar.tsx                     # Reusable avatar component
└── utils/
    ├── dateFormatting.ts              # Date/time formatting helpers
    └── initials.ts                    # Name to initials converter
```

### Helper Utilities to Test & Implement

```tsx
// utils/dateFormatting.ts
export const formatRelativeTime = (date: Date): string => {
  // Returns "2 hours ago", "1 day ago", etc.
};

export const formatMemberSince = (date: Date): string => {
  // Returns "January 2024"
};

// utils/initials.ts
export const getInitials = (name: string): string => {
  // Returns "JD" for "John Doe"
};
```

### Mock Data for Tests
```tsx
const mockUser: User = {
  id: 'user-123',
  name: 'John Doe',
  email: 'john.doe@example.com',
  avatarUrl: 'https://example.com/avatar.jpg',
  memberSince: new Date('2024-01-15')
};

const mockActivities: Activity[] = [
  {
    id: 'act-1',
    type: 'login',
    description: 'Logged in',
    timestamp: new Date(Date.now() - 2 * 60 * 60 * 1000) // 2 hours ago
  },
  {
    id: 'act-2',
    type: 'profile_update',
    description: 'Updated profile',
    timestamp: new Date(Date.now() - 24 * 60 * 60 * 1000) // 1 day ago
  }
];
```

## Acceptance Criteria
- [ ] Comprehensive test suite generated FIRST with React Testing Library
- [ ] All rendering tests pass
- [ ] All interaction tests pass
- [ ] All accessibility tests pass
- [ ] All edge case tests pass
- [ ] UserDashboard component implemented
- [ ] Component passes ALL generated tests
- [ ] Test coverage is 100%
- [ ] Component is fully typed with TypeScript
- [ ] Code follows React best practices
- [ ] Accessible (keyboard navigation, ARIA labels, semantic HTML)

## TDD Workflow
1. **Red Phase:** Generate comprehensive test suite with React Testing Library that will fail
2. **Green Phase:** Implement component to make all tests pass
3. **Refactor Phase:** (Optional) Improve component quality while keeping tests green

## Testing Framework
- React Testing Library
- Jest
- @testing-library/user-event (for interaction tests)
- @testing-library/jest-dom (for matchers)

## Additional Context
This dashboard is a central part of the user experience. The TDD approach ensures we have full test coverage from the start and the component behaves correctly in all scenarios.

**Priority:** High
**Estimated Complexity:** Medium
**Sprint:** Sprint 1
**TDD Required:** YES
**Framework:** React + TypeScript + React Testing Library

# Issue #1: Add User Authentication API Endpoint

**Type:** Feature
**Labels:** `feature`, `backend`, `api`
**Assignee:** ADWS Bot
**Status:** Open

## Description

Implement a REST API endpoint for user authentication using JWT tokens. This endpoint will be the foundation for our authentication system.

## Requirements

### Functional Requirements
1. **POST /api/auth/login** endpoint that accepts:
   - Email (string, required, valid email format)
   - Password (string, required, min 8 characters)

2. **Response on success (200 OK)**:
   ```json
   {
     "success": true,
     "token": "eyJhbGciOiJIUzI1NiIs...",
     "user": {
       "id": "user-123",
       "email": "user@example.com",
       "name": "John Doe"
     },
     "expiresIn": 3600
   }
   ```

3. **Response on failure (401 Unauthorized)**:
   ```json
   {
     "success": false,
     "error": "Invalid credentials",
     "code": "AUTH_FAILED"
   }
   ```

### Non-Functional Requirements
- Password must be validated (min 8 chars, max 128 chars)
- Email must be validated using standard email regex
- JWT token should expire in 1 hour (3600 seconds)
- Proper error handling for:
  - Missing fields (400 Bad Request)
  - Invalid email format (400 Bad Request)
  - Invalid credentials (401 Unauthorized)
  - Server errors (500 Internal Server Error)

### Implementation Details
- Use Pydantic models for request/response validation
- Use FastAPI for endpoint implementation
- JWT secret should be loaded from environment variable `JWT_SECRET`
- Password hashing should use bcrypt or similar
- Include proper type hints
- Follow REST API best practices

### File Structure Expected
```
app/server/
├── api/
│   ├── auth.py          # Authentication endpoints
│   └── models.py        # Pydantic models for auth
└── utils/
    ├── jwt_utils.py     # JWT token generation/validation
    └── password_utils.py # Password hashing/verification
```

## Acceptance Criteria
- [ ] POST /api/auth/login endpoint is implemented
- [ ] Email validation works correctly
- [ ] Password validation works correctly
- [ ] JWT token is generated on successful authentication
- [ ] Proper error responses for all error cases
- [ ] Code follows project conventions
- [ ] Type hints are included
- [ ] Docstrings explain the functionality

## Additional Context
This is a critical feature for the application's security. The implementation should be production-ready with proper error handling and validation.

**Priority:** High
**Estimated Complexity:** Medium
**Sprint:** Sprint 1

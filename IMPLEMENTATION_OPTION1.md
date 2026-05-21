# Authorization Header Implementation - Option 1

## Summary
Implemented automatic Authorization header injection for all API requests using a centralized axios instance. This ensures that Firebase ID tokens are automatically included in every API call without manual configuration.

## Changes Made

### 1. Created `client/src/services/api.ts` (NEW FILE)
- **Purpose**: Centralized axios instance with automatic Authorization header injection
- **Features**:
  - Automatically retrieves Firebase ID token from localStorage
  - Injects `Authorization: Bearer ${token}` header on every request
  - Implements response interceptor to handle token refresh on 401 errors
  - Gracefully redirects to login if token refresh fails

### 2. Updated `client/src/context/AuthContext.tsx`
- **Changed**: Imported `apiClient` from `services/api`
- **Updated `fetchAndApplyPreferences()`**:
  - Now uses `apiClient.get('/api/users/preferences')` 
  - Removed manual header injection (handled by interceptor)
  - Added debug logging for failed requests

- **Updated `signup()`, `login()`, `googleLogin()`**:
  - Now use `apiClient.post()` instead of `axios.post()`
  - Removed manual API_BASE URL construction

### 3. Updated `client/src/pages/PreferencesPage.tsx`
- **Changed**: Imported `apiClient` instead of `axios`
- **Removed**: `getToken()` call from `useAuth()` (no longer needed)
- **Removed**: Manual Authorization header injection
- **Updated**: `APIBase` references removed
- **Improved**: Added error logging to console for debugging

## How It Works

### Request Flow
```
Client makes API call
    ↓
Request Interceptor
    ├─ Get token from localStorage
    ├─ Add Authorization: Bearer ${token} header
    └─ Send request with header
    ↓
Backend receives request
    ├─ Validates token
    └─ Processes request
```

### Token Refresh Flow (Automatic)
```
API returns 401 Unauthorized
    ↓
Response Interceptor detects 401
    ↓
Refresh Token
    ├─ Calls /api/auth/refresh with refresh_token
    ├─ Receives new id_token
    └─ Stores in localStorage
    ↓
Retry Original Request
    └─ With new token in Authorization header
```

## Benefits

✅ **Automatic**: No need to manually get and add token to every request  
✅ **Consistent**: All requests follow the same pattern  
✅ **Resilient**: Automatic token refresh on expiration  
✅ **Clean**: No boilerplate code scattered across components  
✅ **Maintainable**: Central location for auth logic  
✅ **Debugging**: Built-in error logging to console  

## What Gets the Token Automatically

All of these endpoints now receive the Authorization header automatically:

- ✅ `GET /api/users/preferences` - Loads saved preferences
- ✅ `POST /api/users/preferences` - Saves preferences  
- ✅ `POST /api/auth/signup` - Creates account
- ✅ `POST /api/auth/login` - Logs in
- ✅ `POST /api/auth/google` - Google OAuth
- ✅ Any future API endpoints added to the client

## Files Modified

| File | Changes |
|------|---------|
| `client/src/services/api.ts` | **NEW** - Centralized axios with auth interceptors |
| `client/src/context/AuthContext.tsx` | Updated to use `apiClient` instead of `axios` |
| `client/src/pages/PreferencesPage.tsx` | Updated to use `apiClient` instead of `axios` |

## Testing the Fix

### Before (Manual Headers)
```typescript
const token = await getToken();
await axios.get('/api/users/preferences', {
  headers: { Authorization: `Bearer ${token}` }
});
```

### After (Automatic Headers)
```typescript
// Token is added automatically!
await apiClient.get('/api/users/preferences');
```

## Result

Users will now:
1. ✅ See their saved preferences load correctly
2. ✅ Have preferences persist across page refreshes
3. ✅ Get automatic token refreshes on expiration
4. ✅ Get seamless redirects to login if auth fails

## No 401 Errors

The 401 errors were occurring because:
- Token wasn't being sent in the Authorization header (or was missing)
- Token was expired

Now both are handled automatically and transparently to the user.

# Firebase Authentication Implementation - Divinus Project

**Date:** March 26, 2026  
**Project:** Divinus AI Spiritual Assistant  
**Documentation Version:** 1.0

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Frontend Implementation](#frontend-implementation)
3. [Backend Implementation](#backend-implementation)
4. [Authentication Flow](#authentication-flow)
5. [Protected Routes](#protected-routes)
6. [Database Integration](#database-integration)
7. [Token Management](#token-management)
8. [Error Handling](#error-handling)
9. [Security Considerations](#security-considerations)

---

## Architecture Overview

The Divinus project uses a **client-server authentication architecture** with Firebase as the identity provider:

```
┌─────────────────────────────────────────────────────────────┐
│                         CLIENT (React)                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Firebase Auth (Web SDK) - Client-side Authentication│   │
│  │  - Sign Up with email/password                       │   │
│  │  - Sign In with email/password                       │   │
│  │  - Generate ID Tokens (JWT)                          │   │
│  │  - Session Management (onAuthStateChanged)           │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↓ (ID Token)
┌─────────────────────────────────────────────────────────────┐
│                    NETWORK (HTTP/HTTPS)                      │
│  Authorization Header: Bearer <Firebase_ID_Token>           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                      SERVER (Node.js/Express)               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Firebase Admin SDK - Server-side Verification       │   │
│  │  - Verify ID Token against Firebase                  │   │
│  │  - Extract User Claims (uid, email, etc.)            │   │
│  │  - Enforce Authorization on Protected Routes         │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  MongoDB - User Data Persistence                     │   │
│  │  - Store User Preferences (prefs)                    │   │
│  │  - Log User Activity (last_updated)                  │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Key Technologies:
- **Frontend Auth:** Firebase Web SDK (v9+, modular)
- **Backend Verification:** Firebase Admin SDK (Node.js)
- **Database:** MongoDB (user preferences and logs)
- **Token Type:** Firebase ID Token (JWT format)
- **Transport:** HTTPS with Bearer token in Authorization header

---

## Frontend Implementation

### 1. Firebase Configuration (`FrontEnd/src/firebase.js`)

```javascript
import { initializeApp } from "firebase/app";
import { getAuth } from 'firebase/auth';

const firebaseConfig = {
  apiKey: "AIzaSyATsCYCgphhoREeZ8Y3xG-qW5sHxicVlIk",
  authDomain: "divinusai.firebaseapp.com",
  projectId: "divinusai",
  storageBucket: "divinusai.firebasestorage.app",
  messagingSenderId: "790082744156",
  appId: "1:790082744156:web:c9e0f720a72be778949b99",
  measurementId: "G-C4J1H89Z4E"
};

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
```

**What it does:**
- Initializes Firebase with the Divinus project credentials
- Exports the `auth` object (Firebase Authentication instance)
- The `auth` object is used throughout the frontend for all authentication operations

**Configuration Details:**
- `apiKey`: Public API key for browser requests
- `authDomain`: Firebase custom domain for auth redirects
- `projectId`: Unique identifier for the Firebase project ("divinusai")
- `storageBucket`: Cloud Storage bucket for media files
- `appId`: Unique identifier for this web app

---

### 2. Login Component (`FrontEnd/src/pages/Login/Login.jsx`)

The Login component provides both **Sign Up** and **Sign In** functionality:

```javascript
import { createUserWithEmailAndPassword, signInWithEmailAndPassword } from 'firebase/auth'
import { auth } from '../../firebase'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [isSignUp, setIsSignUp] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      if (isSignUp) {
        // Create new user account
        await createUserWithEmailAndPassword(auth, email, password)
      } else {
        // Sign in existing user
        await signInWithEmailAndPassword(auth, email, password)
      }
      // Redirect to preferences page after successful auth
      navigate('/preferences')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    // ... form UI with email/password inputs
  )
}
```

**Key Functions:**

#### `createUserWithEmailAndPassword(auth, email, password)`
- **Purpose:** Register a new user account with Firebase
- **Input:** Firebase auth instance, email, password
- **Output:** UserCredential object containing the new user
- **What happens:**
  1. Firebase validates email format and password strength
  2. Creates new user in Firebase Authentication service
  3. Automatically signs the user in after creation
  4. Generates a Firebase ID token
  5. Stores the token in browser's local storage

#### `signInWithEmailAndPassword(auth, email, password)`
- **Purpose:** Authenticate existing user
- **Input:** Firebase auth instance, email, password
- **Output:** UserCredential object containing user info
- **What happens:**
  1. Firebase verifies email and password against stored credentials
  2. If valid, generates a Firebase ID token
  3. Stores token in browser's local storage
  4. Updates the global auth state

**Flow:**
```
User fills form → Click Sign In/Sign Up
    ↓
handleSubmit() called
    ↓
Firebase API call (createUserWithEmailAndPassword or signInWithEmailAndPassword)
    ↓
User authenticated + ID token generated + stored in browser
    ↓
navigate('/preferences') → Redirect to preferences page
```

---

### 3. Token Generation Utility (`FrontEnd/src/utils/firebase_auth.js`)

```javascript
import { auth } from "../firebase";

export async function getFirebaseToken() {
  const user = auth.currentUser;
  if (!user) throw new Error("User not logged in");

  return await user.getIdToken(/* forceRefresh */ true);
}
```

**Purpose:** Extract and refresh the current user's ID token for API requests

**Function Details:**
- `auth.currentUser`: Firebase property containing the currently logged-in user
- `getIdToken(true)`: 
  - Gets the user's JWT ID token
  - The `true` parameter forces a refresh from Firebase servers
  - Returns a Promise that resolves to the token string

**Use Case:**
```javascript
// In Preferences.jsx
const idToken = await getFirebaseToken();
const res = await fetch(API_ENDPOINT, {
  method: "GET",
  headers: { "Authorization": `Bearer ${idToken}` }
});
```

---

### 4. Auth Context (`FrontEnd/src/context/AuthContext.jsx`)

The AuthContext provides global authentication state to the entire app:

```javascript
import { onAuthStateChanged, signOut } from 'firebase/auth'
import { auth } from '../firebase'

export const AuthContext = createContext()

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (currentUser) => {
      setUser(currentUser)
      setLoading(false)
    })
    return () => unsubscribe()
  }, [])

  const logout = () => signOut(auth)

  return (
    <AuthContext.Provider value={{ user, loading, logout }}>
      {children}
    </AuthContext.Provider>
  )
}
```

**Key Components:**

#### `onAuthStateChanged(auth, callback)`
- **Purpose:** Listen for authentication state changes across the entire app lifecycle
- **How it works:**
  1. When app loads, checks Firebase for any existing session
  2. If user was previously logged in (token in storage), automatically re-authenticates
  3. Calls the callback whenever auth state changes (login, logout, token refresh, etc.)
  4. Returns an unsubscribe function to clean up listener

**Auth State Flow:**
```
App loads
    ↓
onAuthStateChanged listener activated
    ↓
Check for existing token in browser storage
    ↓
If found → Validate token → Set user state
If not found → Set user state to null
    ↓
loading = false → App can render
```

#### Context Value:
- `user`: Current user object (null if not logged in)
  - Contains: uid, email, displayName, photoURL, etc.
- `loading`: Boolean indicating if auth state is still initializing
- `logout()`: Function to sign out user

---

### 5. App Routing & Protected Routes (`FrontEnd/src/App.jsx`)

```javascript
import { useContext } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthContext } from './context/AuthContext'

function ProtectedRoute({ children }) {
  const { user, loading } = useContext(AuthContext)
  
  if (loading) return <div>Loading...</div>
  
  return user ? children : <Navigate to="/login" />
}

const App = () => {
  return (
    <Routes>
      <Route path="/" element={<Hero />} />
      <Route path="/login" element={<Login />} />
      
      <Route 
        path="/preferences" 
        element={
          <ProtectedRoute>
            <Preferences />
          </ProtectedRoute>
        } 
      />
      
      <Route 
        path="/chat" 
        element={
          <ProtectedRoute>
            <ChatLayout />
          </ProtectedRoute>
        } 
      />
    </Routes>
  )
}
```

**Protected Route Logic:**
```
User tries to access /chat
    ↓
ProtectedRoute component renders
    ↓
Check: Is user loading? → Show loading spinner
    ↓
Check: Is user logged in? 
  Yes → Render ChatLayout component
  No → Redirect to /login
```

This ensures unauthenticated users cannot access protected pages.

---

### 6. User Preferences Management (`FrontEnd/src/pages/Preferences/Preferences.jsx`)

After login, users go to the preferences page to set their profile:

```javascript
import { auth } from '../../firebase'
import API_ENDPOINTS from '../../config/api'

export default function Preferences() {
  const [name, setName] = useState('')
  const [religion, setReligion] = useState('')
  const [favGod, setFavGod] = useState('')

  // Load preferences from backend on mount
  useEffect(() => {
    async function loadPrefs() {
      const user = auth.currentUser
      if (!user) return

      const idToken = await user.getIdToken(false)

      const res = await fetch(API_ENDPOINTS.GET_USER_PREFS, {
        method: "GET",
        headers: { "Authorization": `Bearer ${idToken}` }
      })

      const data = await res.json()
      if (data.found && data.data) {
        // Populate form with existing preferences
        setName(data.data.prefs.name || '')
        setReligion(data.data.prefs.religion || '')
        setFavGod(data.data.prefs.favGod || '')
      }
    }

    loadPrefs()
  }, [])

  // Save preferences to backend
  const handleSubmit = async (e) => {
    e.preventDefault()

    const user = auth.currentUser
    if (!user) return

    const idToken = await user.getIdToken(false)

    const res = await fetch(API_ENDPOINTS.SAVE_USER_PREFS, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${idToken}`
      },
      body: JSON.stringify({ 
        prefs: { name, religion, favGod }
      })
    })

    if (res.ok) {
      navigate("/chat")
    }
  }
}
```

**API Integration:**
- Gets fresh ID token: `user.getIdToken(false)`
- Sends token in Authorization header
- Backend verifies token and associates preferences with user's UID

---

## Backend Implementation

### 1. Firebase Admin SDK Configuration (`BackEnd/server/config/firebase.js`)

```javascript
const admin = require('firebase-admin');
const path = require('path');

let initialized = false;

function initFirebase() {
  if (initialized) return;

  const credPath = process.env.GOOGLE_APPLICATION_CREDENTIALS;
  if (!credPath) {
    throw new Error('❌ Missing Firebase credentials path');
  }

  try {
    const serviceAccount = require(path.resolve(credPath));
    admin.initializeApp({
      credential: admin.credential.cert(serviceAccount)
    });
    console.log('✅ Firebase initialized');
    initialized = true;
  } catch (e) {
    throw new Error(`❌ Firebase initialization failed: ${e.message}`);
  }
}

module.exports = { initFirebase, admin };
```

**Key Details:**

#### Service Account Credentials
- `GOOGLE_APPLICATION_CREDENTIALS` environment variable points to the service account JSON file
- File: `divinusai-firebase-adminsdk-fbsvc-1ffb50712c.json`
- Contains private key, project ID, and credentials for admin operations
- **NEVER commit this file to version control** (add to .gitignore)

#### Firebase Admin Initialization
- `admin.initializeApp()`: Initializes Firebase Admin SDK with credentials
- Allows server to:
  - Verify ID tokens from clients
  - Perform privileged operations (create/delete users)
  - Access Firebase services (Realtime Database, Cloud Firestore, etc.)
- Singleton pattern: Only initialized once per server startup

---

### 2. Authentication Middleware (`BackEnd/server/middleware/auth.js`)

This is the **core of server-side authentication**:

```javascript
const { admin } = require('../config/firebase');

async function getUserFromToken(req, res, next) {
  const authHeader = req.headers.authorization || '';

  if (!authHeader.startsWith('Bearer ')) {
    return res.status(401).json({ error: 'Missing Authorization token' });
  }

  const idToken = authHeader.replace('Bearer ', '').trim();

  try {
    const decoded = await admin.auth().verifyIdToken(idToken);
    req.user = decoded;
    console.log(`[Auth] ✓ User authenticated: ${decoded.uid} (${decoded.email})`);
    next();
  } catch (e) {
    const errorMsg = e.message;
    if (errorMsg.includes('used too early') || errorMsg.includes('clock')) {
      return res.status(401).json({ 
        error: 'System clock out of sync. Please sync your system time.' 
      });
    }
    return res.status(401).json({ error: 'Invalid token', details: errorMsg });
  }
}

module.exports = { getUserFromToken };
```

**Complete Token Verification Process:**

1. **Extract Token from Header**
   ```javascript
   const authHeader = req.headers.authorization; // "Bearer <token>"
   const idToken = authHeader.replace('Bearer ', '').trim(); // Extract token
   ```

2. **Verify Token Signature**
   ```javascript
   const decoded = await admin.auth().verifyIdToken(idToken);
   ```
   The admin SDK:
   - Downloads Firebase's public key certificates
   - Verifies the token's digital signature
   - Checks token expiration time
   - Validates issuer and audience claims

3. **Extract User Claims**
   ```javascript
   // decoded object contains:
   {
     uid: "fkDj0bsaxhbvEYj7A3ialQjAOcx1", // Unique user ID
     email: "user@example.com",
     email_verified: false,
     auth_time: 1711234567,
     user_id: "fkDj0bsaxhbvEYj7A3ialQjAOcx1",
     iat: 1711234567,      // Issued at
     exp: 1711238167,      // Expiration time
     // ... other claims
   }
   ```

4. **Attach to Request & Continue**
   ```javascript
   req.user = decoded; // Store claims in request object
   next(); // Proceed to route handler
   ```

**Token Verification Diagram:**
```
Client Request
    ↓
Authorization: Bearer <token>
    ↓
Extract token string
    ↓
admin.auth().verifyIdToken(token)
    ↓
Firebase Admin SDK:
  1. Check token signature (cryptographic verification)
  2. Check expiration time
  3. Check issuer (must be Firebase)
  4. Decode JWT claims
    ↓
Token valid? 
  Yes → req.user = {uid, email, ...} → next()
  No → res.status(401).json({error}) → Stop
```

**Error Handling:**
- `ENOENT: Missing Authorization token` → 401 Unauthorized
- `INVALID_TOKEN: Invalid signature` → 401 Unauthorized
- `CREDENTIAL_MISMATCH: Token used too early` → 401 (Clock skew issue)

---

### 3. User Model (`BackEnd/server/models/User.js`)

```javascript
const mongoose = require('mongoose');

const userSchema = new mongoose.Schema({
  uid: { type: String, required: true, unique: true },
  email: String,
  prefs: mongoose.Schema.Types.Mixed,
  last_updated: { type: Date, default: Date.now }
}, { collection: 'UserLog' });

module.exports = mongoose.model('User', userSchema);
```

**Schema Details:**
- `uid`: Firebase UID (primary key, matches client's auth.currentUser.uid)
- `email`: User's email address (denormalized from Firebase for quick lookup)
- `prefs`: User preferences object (religion, favorite god, name, age, etc.)
- `last_updated`: Timestamp of last preference update
- Collection name: `UserLog` (MongoDB collection)

**Why store in MongoDB?**
- Firebase stores authentication only
- MongoDB stores application-specific user data (preferences)
- Separates concerns: Auth vs. App Data

---

### 4. User Routes (`BackEnd/server/routes/user.js`)

#### POST /api/users - Save Preferences

```javascript
router.post('/', getUserFromToken, async (req, res) => {
  try {
    const uid = req.user.uid; // From verified token
    const email = req.user.email;
    const { prefs = {} } = req.body;

    const db = getDb();
    const usersCollection = db.collection('UserLog');

    const user = await usersCollection.findOneAndUpdate(
      { uid }, // Find user by Firebase UID
      {
        $set: {
          uid,
          email,
          prefs,
          last_updated: new Date()
        }
      },
      { upsert: true, returnDocument: 'after' }
    );

    res.json({ success: true });
  } catch (e) {
    res.status(500).json({ error: `Database error: ${e.message}` });
  }
});
```

**Flow:**
```
POST /api/users with "Authorization: Bearer <token>"
    ↓
getUserFromToken middleware:
  Verify token → req.user = {uid, email, ...}
    ↓
Extract prefs from request body
    ↓
findOneAndUpdate:
  Match: User document with uid = "fkDj0bsaxhbvEYj7A3ialQjAOcx1"
  Update: Set preferences, email, timestamp
  If not found: Create new document (upsert: true)
    ↓
Return success: { success: true }
```

**Database Operation:**
```javascript
db.collection('UserLog').findOneAndUpdate(
  { uid: "fkDj0bsaxhbvEYj7A3ialQjAOcx1" },
  { $set: { email, prefs, last_updated } },
  { upsert: true, returnDocument: 'after' }
)
```

#### GET /api/users - Load Preferences

```javascript
router.get('/', getUserFromToken, async (req, res) => {
  try {
    const uid = req.user.uid;
    const db = getDb();
    const usersCollection = db.collection('UserLog');
    
    const doc = await usersCollection.findOne(
      { uid }, 
      { projection: { _id: 0 } } // Exclude MongoDB _id
    );
    
    return res.json({ 
      found: !!doc, 
      data: doc 
    });
  } catch (e) {
    return res.status(500).json({ error: `Database error: ${e.message}` });
  }
});
```

**Response:**
```json
{
  "found": true,
  "data": {
    "uid": "fkDj0bsaxhbvEYj7A3ialQjAOcx1",
    "email": "user@example.com",
    "prefs": {
      "name": "Andruni Tatte",
      "age": "25",
      "religion": "Hinduism",
      "favGod": "Vishnu"
    },
    "last_updated": "2026-03-26T15:30:00Z"
  }
}
```

#### DELETE /api/users - Clear Preferences

```javascript
router.delete('/', getUserFromToken, async (req, res) => {
  try {
    const uid = req.user.uid;
    const db = getDb();
    const usersCollection = db.collection('UserLog');

    await usersCollection.findOneAndUpdate(
      { uid },
      { $set: { prefs: {}, last_updated: new Date() } }
    );

    res.json({ success: true, message: 'Preferences cleared' });
  } catch (e) {
    res.status(500).json({ error: `Database error: ${e.message}` });
  }
});
```

**Operation:** Clears all preferences for the user while keeping the account

---

## Authentication Flow

### Complete Authentication Journey

```
╔═══════════════════════════════════════════════════════════════════════════╗
║                          COMPLETE AUTH FLOW                               ║
╚═══════════════════════════════════════════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE 1: USER REGISTRATION/LOGIN (Frontend)                            │
└─────────────────────────────────────────────────────────────────────────┘

    User visits /login
         ↓
    [Login Component Renders]
    - Email input
    - Password input
    - Sign Up vs Sign In toggle
         ↓
    User enters credentials & clicks "Sign Up" OR "Sign In"
         ↓
    handleSubmit() called
         ↓
    if (isSignUp) {
      createUserWithEmailAndPassword(auth, email, password)
    } else {
      signInWithEmailAndPassword(auth, email, password)
    }
         ↓
    [Firebase Client SDK makes request to Firebase servers]
    - Validates email format
    - Hashes password (bcrypt)
    - Creates/Verifies user account
         ↓
    User successfully authenticated ✓
         ↓
    [Firebase automatically generates ID Token (JWT)]
    Token stored in browser's localStorage
         ↓
    navigate('/preferences')


┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE 2: AUTH STATE SYNCHRONIZATION (On App Load)                      │
└─────────────────────────────────────────────────────────────────────────┘

    App.jsx mounts
         ↓
    <AuthProvider> component activates
         ↓
    onAuthStateChanged(auth, callback) listener starts
         ↓
    [Firebase checks browser storage for existing token]
         ↓
    Valid token found?
         ├─ Yes: Token is still valid
         │   ↓
         │   Restore user state from token
         │   setUser(currentUser) with user data
         │   loading = false
         │
         └─ No: No token or expired
             ↓
             setUser(null)
             loading = false
         ↓
    AuthContext now reflects current auth state


┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE 3: ROUTE PROTECTION                                              │
└─────────────────────────────────────────────────────────────────────────┘

    User navigates to /chat
         ↓
    <ProtectedRoute> checks auth state
         ↓
    loading? 
         ├─ Yes: Show loading spinner
         └─ No: Continue
         ↓
    user exists?
         ├─ Yes: Render ChatLayout ✓
         └─ No: Navigate to /login


┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE 4: API REQUEST WITH AUTHENTICATION (Frontend)                    │
└─────────────────────────────────────────────────────────────────────────┘

    User fills preferences form
         ↓
    Clicks "Save"
         ↓
    handleSubmit() called
         ↓
    Get fresh token:
    idToken = await auth.currentUser.getIdToken(forceRefresh=true)
         ↓
    [Token might be refreshed from Firebase if near expiration]
         ↓
    Make API request with token:
    
    fetch('/api/users', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${idToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ prefs: {...} })
    })
         ↓
    Request sent to server


┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE 5: SERVER-SIDE TOKEN VERIFICATION                                │
└─────────────────────────────────────────────────────────────────────────┘

    Express receives POST /api/users request
         ↓
    getUserFromToken middleware executes
         ↓
    Extract Authorization header:
    "Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6...truncated..."
         ↓
    Extract token string (remove "Bearer " prefix)
         ↓
    admin.auth().verifyIdToken(idToken)
         ↓
    [Firebase Admin SDK performs cryptographic verification]
    
    Steps:
    1. Download Firebase's public key certificates
    2. Verify JWT signature using public key
    3. Check token expiration (exp claim)
    4. Check issued-at time (iat claim)
    5. Verify issuer is Firebase
    6. Decode JWT payload
         ↓
    Signature valid?
         ├─ Yes: Token is authentic and not tampered
         │   ↓
         │   decoded = {
         │     uid: "fkDj0bsaxhbvEYj7A3ialQjAOcx1",
         │     email: "user@example.com",
         │     email_verified: false,
         │     auth_time: 1711234567,
         │     iat: 1711234567,
         │     exp: 1711238167,
         │     ... other claims
         │   }
         │   ↓
         │   req.user = decoded
         │   next() // Continue to route handler
         │
         └─ No: Invalid signature or expired
             ↓
             return 401 Unauthorized


┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE 6: SAVE USER DATA (Backend)                                      │
└─────────────────────────────────────────────────────────────────────────┘

    Route handler executes (auth verified ✓)
         ↓
    Extract uid from verified request:
    uid = req.user.uid // "fkDj0bsaxhbvEYj7A3ialQjAOcx1"
         ↓
    Extract preferences from request body:
    prefs = { name: "Andruni", religion: "Hinduism", ... }
         ↓
    MongoDB operation:
    db.collection('UserLog').findOneAndUpdate(
      { uid: "fkDj0bsaxhbvEYj7A3ialQjAOcx1" },
      {
        $set: {
          uid,
          email,
          prefs,
          last_updated: new Date()
        }
      },
      { upsert: true } // Create if not exists
    )
         ↓
    Database updated ✓
         ↓
    Return response: { success: true }


┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE 7: SUBSEQUENT API CALLS (Automatic Token Refresh)                │
└─────────────────────────────────────────────────────────────────────────┘

    User makes another API call
         ↓
    getIdToken(forceRefresh=true)
         ↓
    Token near expiration?
         ├─ Yes: Request new token from Firebase
         │   ↓
         │   Firebase validates refresh token
         │   Returns new ID token
         │
         └─ No: Return cached token
         ↓
    Send request with fresh token
         ↓
    Server verifies ✓


┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE 8: LOGOUT                                                        │
└─────────────────────────────────────────────────────────────────────────┘

    User clicks logout button
         ↓
    logout() from AuthContext called
         ↓
    signOut(auth)
         ↓
    [Firebase clears tokens from localStorage]
         ↓
    setUser(null)
         ↓
    ProtectedRoutes now redirect to /login
         ↓
    User session ended ✓
```

---

## Protected Routes

### Route Protection Mechanism

The app uses a **ProtectedRoute wrapper component** to enforce authentication:

```javascript
function ProtectedRoute({ children }) {
  const { user, loading } = useContext(AuthContext)
  
  if (loading) return <div className="loading">Loading...</div>
  
  return user ? children : <Navigate to="/login" />
}
```

**Protected Routes:**
- `/preferences` - Set user preferences (must be logged in)
- `/chat` - Chat with spiritual guide (must be logged in)
- `/feed` - Feed of content (must be logged in)

**Public Routes:**
- `/` - Home page (Hero component)
- `/login` - Login/Sign up page

**Route Guard Table:**

| Route | Protected | Purpose |
|-------|-----------|---------|
| `/` | ❌ No | Landing page, accessible to all |
| `/login` | ❌ No | Login page, accessible to all |
| `/preferences` | ✅ Yes | Set religion, favorite god, name, age |
| `/chat` | ✅ Yes | Chat with AI spiritual guide |
| `/feed` | ✅ Yes | View spiritual content feed |

---

## Database Integration

### MongoDB User Collection Schema

**Collection Name:** `UserLog`

**Document Structure:**
```javascript
{
  "_id": ObjectId("507f1f77bcf86cd799439011"),
  "uid": "fkDj0bsaxhbvEYj7A3ialQjAOcx1",  // Firebase UID (unique)
  "email": "user@example.com",              // User email (from Firebase)
  "prefs": {
    "name": "Andruni Tatte",
    "age": "25",
    "religion": "Hinduism",
    "favGod": "Vishnu"
  },
  "last_updated": ISODate("2026-03-26T15:30:00Z")
}
```

### Data Flow Between Services

```
Firebase (Auth Only)          MongoDB (Preferences)
├─ uid                        ├─ uid (links to Firebase)
├─ email                      ├─ email (cached)
├─ password (hashed)          ├─ prefs (app-specific)
└─ auth_time                  └─ last_updated
```

### Why This Architecture?

1. **Separation of Concerns:**
   - Firebase handles authentication (secure, scalable)
   - MongoDB handles application data (user preferences)

2. **Security:**
   - Passwords never leave Firebase
   - Server never sees plaintext passwords
   - Token verification ensures request authenticity

3. **Flexibility:**
   - Can change preferences without affecting auth
   - Can extend user data without Firebase schema migration
   - Apps can share Firebase project but have separate databases

---

## Token Management

### Firebase ID Token Details

**Token Type:** JWT (JSON Web Token)

**Token Payload Example:**
```javascript
{
  "iss": "https://securetoken.google.com/divinusai",
  "aud": "divinusai",
  "auth_time": 1711234567,
  "user_id": "fkDj0bsaxhbvEYj7A3ialQjAOcx1",
  "sub": "fkDj0bsaxhbvEYj7A3ialQjAOcx1",
  "iat": 1711234567,
  "exp": 1711238167,  // Expires in 1 hour
  "email": "user@example.com",
  "email_verified": false,
  "firebase": {
    "identities": { "email": ["user@example.com"] },
    "sign_in_provider": "password"
  }
}
```

**Key Claims:**
- `iss`: Issuer (must be Firebase)
- `aud`: Audience (must match project ID)
- `sub`/`user_id`: Subject (Firebase UID)
- `iat`: Issued at time
- `exp`: Expiration time (usually 1 hour from issue)
- `email`: User's email
- `email_verified`: Whether email is verified

### Token Lifecycle

```
Login
  ↓
Create token (exp = now + 1 hour)
  ↓
Store in browser localStorage
  ↓
Include in API requests (Authorization header)
  ↓
Server verifies token signature & expiration
  ↓
Token near expiration (30+ min remaining)?
  ├─ Yes: getIdToken(forceRefresh=true) requests new token
  │   ↓
  │   Firebase validates refresh token
  │   Issues new ID token
  │
  └─ No: Reuse cached token
  ↓
Token expired (exp < now)?
  ├─ Yes: getIdToken() triggers automatic refresh
  │   ↓
  │   New token obtained
  │
  └─ No: Continue using token
  ↓
User logs out
  ↓
signOut(auth) clears tokens from storage
  ↓
All tokens invalidated
```

### Token Refresh Flow

**Automatic Refresh (Client-side):**
```javascript
// In Preferences.jsx
const idToken = await auth.currentUser.getIdToken(forceRefresh=true);
//                                                   ↑
//                                   Forces new token from Firebase
```

**When is refresh triggered?**
1. First time in request: Always gets fresh token
2. Token expires: Automatically requests new one
3. `forceRefresh=true`: Bypasses cache, always requests new token

**Why refresh tokens are important:**
- Limits damage if token is stolen (only 1 hour valid)
- Allows backend to revoke access by blocking token verification
- Sessions naturally expire even if user forgets to logout

---

## Error Handling

### Frontend Error Handling

**Login Component:**
```javascript
const handleSubmit = async (e) => {
  e.preventDefault()
  setError('')
  setLoading(true)

  try {
    if (isSignUp) {
      await createUserWithEmailAndPassword(auth, email, password)
    } else {
      await signInWithEmailAndPassword(auth, email, password)
    }
    navigate('/preferences')
  } catch (err) {
    setError(err.message)  // Display Firebase error to user
  } finally {
    setLoading(false)
  }
}
```

**Common Firebase Errors:**

| Error | Message | Cause |
|-------|---------|-------|
| `auth/invalid-email` | Invalid email address | Email format validation |
| `auth/weak-password` | Password too weak | Minimum requirements not met |
| `auth/email-already-in-use` | Email already exists | Sign up with existing email |
| `auth/wrong-password` | Incorrect password | Login with wrong password |
| `auth/user-not-found` | User doesn't exist | Login with non-existent email |
| `auth/too-many-requests` | Too many failed attempts | Account temporarily locked |

### Backend Error Handling

**Auth Middleware:**
```javascript
try {
  const decoded = await admin.auth().verifyIdToken(idToken);
  req.user = decoded;
  next();
} catch (e) {
  const errorMsg = e.message;
  
  // Clock skew error
  if (errorMsg.includes('used too early') || errorMsg.includes('clock')) {
    return res.status(401).json({ 
      error: 'System clock out of sync. Please sync your system time.' 
    });
  }
  
  // Generic token error
  return res.status(401).json({ 
    error: 'Invalid token', 
    details: errorMsg 
  });
}
```

**Common Backend Errors:**

| Error | Status | Cause |
|-------|--------|-------|
| `Missing Authorization token` | 401 | No Bearer token in header |
| `Invalid token signature` | 401 | Token tampered with |
| `Token used too early` | 401 | System clock is ahead (clock skew) |
| `Token expired` | 401 | Token older than 1 hour |
| `Database error` | 500 | MongoDB connection/operation failure |

### User-Friendly Error Messages

The app displays errors to users:

```
❌ Invalid email address
❌ Password should be at least 6 characters
❌ Email already in use
❌ Authentication failed. Please try again.
❌ System clock out of sync. Please sync your system time.
```

---

## Security Considerations

### 1. Token Storage

**Current Implementation:** Browser localStorage

```javascript
// Firebase automatically stores in:
localStorage.getItem('firebase:authUser:[apiKey]:[projectId]')
```

**Security Level:** Medium
- Vulnerable to XSS attacks (JavaScript can access localStorage)
- Protected from CSRF (token required in request)
- Automatically cleared on logout/browser close

**Recommendations:**
- Don't store sensitive data in localStorage beyond tokens
- Implement Content Security Policy (CSP) to prevent XSS
- Use httpOnly cookies as alternative (requires backend setup)

### 2. Token Transmission

**Current Method:** Authorization header with Bearer scheme

```
GET /api/users
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6...token...
```

**Security Features:**
- ✅ Token not in URL (prevents logging, caching)
- ✅ Bearer scheme is standard OAuth 2.0
- ✅ HTTPS required in production (prevents man-in-the-middle)
- ⚠️ Token still vulnerable if HTTPS intercepted

**Best Practice:** Always use HTTPS for production

### 3. Server-Side Token Verification

**Security Measures:**
```javascript
// 1. Verify signature using Firebase's public key
await admin.auth().verifyIdToken(idToken)

// 2. Checks performed automatically:
- JWT signature is valid (not tampered)
- Token issuer is Firebase
- Token audience matches project ID
- Token is not expired
- Token was issued after user login
```

**Cannot Be Faked:**
- Signature verification requires Firebase's private key (secret)
- Only Firebase servers have the private key
- Clients cannot generate valid tokens

### 4. User Identification

**Frontend (Client-side):**
```javascript
const user = auth.currentUser;
// Local data, can be modified by user (don't trust)
```

**Backend (Server-side):**
```javascript
const decoded = await admin.auth().verifyIdToken(idToken);
const uid = decoded.uid;
// Verified by Firebase, safe to trust
```

**Rule:** Always extract `uid` from verified token on server, never trust client-provided IDs.

### 5. Database Access Control

**Current Implementation:**
```javascript
const uid = req.user.uid;  // From verified token

db.collection('UserLog').findOneAndUpdate(
  { uid },  // Only access own document
  { $set: { prefs } }
)
```

**Security:**
- ✅ User can only modify their own preferences (filtered by uid)
- ✅ MongoDB doesn't enforce this (backend does)
- ⚠️ Backend must always filter by authenticated user's uid

**Best Practice:** Always include `uid` in query filter:
```javascript
// ✅ Secure
db.collection('UserLog').findOne({ uid: req.user.uid })

// ❌ Insecure (trusts user-provided uid)
db.collection('UserLog').findOne({ uid: req.body.uid })
```

### 6. Credential Management

**Safe Practices:**
```javascript
// ✅ Good: Environment variables for credentials
const credPath = process.env.GOOGLE_APPLICATION_CREDENTIALS;

// ✅ Good: Don't log sensitive data
// admin credentials are not logged

// ❌ Bad: Hardcoding credentials
const credentials = {
  "private_key": "-----BEGIN PRIVATE KEY-----...",
  "client_email": "firebase-adminsdk@...",
}

// ❌ Bad: Committing credentials to GitHub
git add divinusai-firebase-adminsdk-fbsvc-1ffb50712c.json
```

**File Permissions (.gitignore):**
```
# Never commit service account file
BackEnd/divinusai-firebase-adminsdk-fbsvc-1ffb50712c.json

# Never commit .env files with secrets
BackEnd/.env
FrontEnd/.env
```

### 7. CORS (Cross-Origin Resource Sharing)

**Current Implementation:**
```javascript
const cors = require('cors');
app.use(cors());
```

**What it does:**
- Allows frontend (different domain) to make requests to backend
- Sends `Access-Control-Allow-*` headers
- Browsers enforce CORS rules

**Production Recommendation:**
```javascript
// Instead of allowing all origins:
app.use(cors({
  origin: 'https://divinus.example.com',
  credentials: true
}))
```

### 8. Password Security

**Firebase Handles:**
- ✅ Password hashing (bcrypt)
- ✅ Salting (unique per user)
- ✅ Password complexity requirements
- ✅ Rate limiting (account lockout after failed attempts)

**Your Responsibilities:**
- ✅ Always use HTTPS (passwords visible in transit otherwise)
- ✅ Never log passwords
- ✅ Educate users about strong passwords

---

## Summary

### Authentication Architecture
```
Client (Firebase Web SDK) ↔ Token ↔ Server (Firebase Admin SDK) ↔ MongoDB
```

### Key Components
1. **Firebase Web SDK** - Client-side: Sign up/in, token generation
2. **Firebase Admin SDK** - Server-side: Token verification
3. **AuthContext** - Global state management
4. **Protected Routes** - Enforce authentication
5. **MongoDB** - Store user preferences

### Security Layers
1. Firebase handles password security (hashing, salting)
2. JWT token signature verification (cryptographic)
3. Token expiration (1 hour)
4. Server-side uid filtering (access control)
5. HTTPS transport (in production)

### Token Flow
```
Sign Up/In → Token generated → Stored in localStorage → 
Included in API requests → Verified by server → User identified →
Data manipulated safely
```

### Best Practices Implemented
- ✅ Tokens verified on every request
- ✅ User data filtered by authenticated user's uid
- ✅ Error handling with appropriate HTTP status codes
- ✅ Separation of Firebase auth from app data (MongoDB)
- ✅ Automatic token refresh
- ✅ Protected routes prevent unauthorized access

---

**End of Documentation**

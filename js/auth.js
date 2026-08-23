// ======================================================
// ZigZag Authentication
// ======================================================

let accessToken = null;
let currentUser = null;

let refreshTimer = null;
let refreshPromise = null;

const LOGIN_PATH = "/auth/login";


// ======================================================
// Access Token
// ======================================================

function setAccessToken(token) {
    accessToken = token;
}

function getAccessToken() {
    return accessToken;
}

function clearAccessToken() {
    accessToken = null;
}


// ======================================================
// Current User
// ======================================================

function setUser(user) {
    currentUser = user;
    updateNavbar(user);
}

function getUser() {
    return currentUser;
}

function isLoggedIn() {
    return accessToken !== null;
}


// ======================================================
// Decode JWT
// ======================================================

function parseJwt(token) {
    try {
        return JSON.parse(atob(token.split(".")[1]));
    } catch {
        return null;
    }
}


// ======================================================
// Navbar
// ======================================================

function updateNavbar(user = null) {

    const loginBtn = document.getElementById("login-btn");
    const profileBtn = document.getElementById("profile-btn");

    if (!loginBtn || !profileBtn) {
        return;
    }

    if (user) {

        // Logged in
        loginBtn.classList.add("hidden");
        profileBtn.classList.remove("hidden");

        const profileName = document.getElementById("profile-name");
        const profileEmail = document.getElementById("profile-email");

        if (profileName) {
            profileName.textContent = `Hello, ${user.first_name}`;
        }

        if (profileEmail) {
            profileEmail.textContent = user.email;
        }

    } else {

        // Not logged in
        profileBtn.classList.add("hidden");
        loginBtn.classList.remove("hidden");

    }
}


// ======================================================
// Auto Refresh Timer
// ======================================================

function startRefreshTimer(token) {

    if (refreshTimer) {
        clearTimeout(refreshTimer);
    }

    const payload = parseJwt(token);

    if (!payload || !payload.exp) {
        return;
    }

    const expiresAt = payload.exp * 1000;
    const now = Date.now();

    // Refresh 60 seconds before expiry
    const timeout = Math.max(expiresAt - now - 60000, 5000);

    refreshTimer = setTimeout(async () => {
        await refreshAccessToken();
    }, timeout);
}


// ======================================================
// Refresh Access Token
// ======================================================

async function refreshAccessToken() {

    if (refreshPromise) {
        return refreshPromise;
    }

    refreshPromise = (async () => {

        try {

            const response = await fetch("/auth/refresh", {
                method: "POST",
                credentials: "include",
            });

            if (!response.ok) {
                console.error(
                    "[auth debug] /auth/refresh failed:",
                    response.status,
                    response.statusText
                );
                throw new Error();
            }

            const data = await response.json();

            setAccessToken(data.access_token);

            if (data.user) {
                setUser(data.user);
            }

            startRefreshTimer(data.access_token);

            return true;

        } catch (err) {

            console.error("[auth debug] refreshAccessToken failed:", err);

            // Not logged in (or session expired) — just fall back to
            // guest state. Do NOT force-redirect to the login page;
            // the user stays right where they are.
            clearAccessToken();

            currentUser = null;

            updateNavbar();

            return false;

        } finally {
            refreshPromise = null;
        }

    })();

    return refreshPromise;
}


// ======================================================
// Login Success
// ======================================================

function loginSuccess(access_token, user = null) {

    setAccessToken(access_token);

    if (user) {
        setUser(user);
    }

    startRefreshTimer(access_token);
}


// ======================================================
// Logout
// ======================================================

async function logout() {

    const logoutBtn = document.getElementById("logout-btn");

    if (logoutBtn) {

        logoutBtn.style.pointerEvents = "none";
        logoutBtn.style.opacity = "0.6";

        logoutBtn.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg"
                 width="16"
                 height="16"
                 viewBox="0 0 24 24"
                 fill="none"
                 stroke="currentColor"
                 stroke-width="2">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
                <polyline points="16 17 21 12 16 7"/>
                <line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
            Logging out...
        `;
    }

    try {
        const res = await authFetch("/auth/logout", { method: "POST" });

        if (!res.ok) {
            console.error("Logout request failed:", res.status);
        }
    } catch (e) {
        console.error(e);
    }

    clearAccessToken();
    currentUser = null;

    if (refreshTimer) {
        clearTimeout(refreshTimer);
    }

    window.location.href = "/?toast=logout_success";
}


// ======================================================
// Logout Button
// ======================================================

document.addEventListener("click", (e) => {

    if (e.target.closest("#logout-btn")) {
        logout();
    }

});


// ======================================================
// Authenticated Fetch
// ======================================================

async function authFetch(url, options = {}) {

    if (!accessToken) {

        const ok = await refreshAccessToken();

        if (!ok) {
            throw new Error("Not authenticated");
        }
    }

    options.credentials = "include";

    options.headers = {
        ...(options.headers || {}),
        Authorization: `Bearer ${accessToken}`,
    };

    let response = await fetch(url, options);

    if (response.status === 401) {

        const ok = await refreshAccessToken();

        if (!ok) {
            throw new Error("Session expired");
        }

        options.headers.Authorization = `Bearer ${accessToken}`;

        response = await fetch(url, options);
    }

    return response;
}


// ======================================================
// Initialize Authentication
// ======================================================

(async function () {

    // Login page doesn't need auto refresh
    if (window.location.pathname === LOGIN_PATH) {
        updateNavbar();
        return;
    }

    await refreshAccessToken();

})();


// ======================================================
// Global Access
// ======================================================

window.auth = {
    loginSuccess,
    logout,
    authFetch,
    refreshAccessToken,
    getAccessToken,
    getUser,
    isLoggedIn,
};
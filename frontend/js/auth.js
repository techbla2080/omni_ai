/**
 * OmniAI Authentication Module
 * Steps 56-62: Login, Signup, Password Reset, Profile, Session Management
 * 
 * FIXES APPLIED:
 * 1. refreshAccessToken() - sends JSON body instead of query param
 * 2. forgotPassword() - sends JSON body instead of query param
 * 3. logout() - removed non-existent /auth/logout endpoint call
 * 4. login() - fetches user profile after login (backend doesn't return user object)
 * 5. changePassword() - fixed URL to /auth/me/password with PUT method
 * 6. updateProfile() - sends JSON body instead of query param
 * 7. Renamed API_BASE to AUTH_API_BASE to avoid conflict with app.js
 */

const AUTH_API_BASE = '/api/v1';

// ============================================================================
// TOKEN MANAGEMENT (Step 60)
// ============================================================================

function storeTokens(accessToken, refreshToken, rememberMe = false) {
    if (rememberMe) {
        localStorage.setItem('omniai_access_token', accessToken);
        localStorage.setItem('omniai_refresh_token', refreshToken);
    } else {
        sessionStorage.setItem('omniai_access_token', accessToken);
        sessionStorage.setItem('omniai_refresh_token', refreshToken);
    }
}

function getAccessToken() {
    return localStorage.getItem('omniai_access_token') || 
           sessionStorage.getItem('omniai_access_token');
}

function getRefreshToken() {
    return localStorage.getItem('omniai_refresh_token') || 
           sessionStorage.getItem('omniai_refresh_token');
}

function clearTokens() {
    localStorage.removeItem('omniai_access_token');
    localStorage.removeItem('omniai_refresh_token');
    localStorage.removeItem('omniai_user');
    sessionStorage.removeItem('omniai_access_token');
    sessionStorage.removeItem('omniai_refresh_token');
}

function isAuthenticated() {
    return !!getAccessToken();
}

function storeUser(user) {
    localStorage.setItem('omniai_user', JSON.stringify(user));
}

function getStoredUser() {
    const user = localStorage.getItem('omniai_user');
    return user ? JSON.parse(user) : null;
}

// ============================================================================
// API HELPERS
// ============================================================================

async function authFetch(url, options = {}) {
    const token = getAccessToken();
    
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };
    
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    
    const response = await fetch(url, { ...options, headers });
    
    // Handle 401 - try refresh token
    if (response.status === 401 && getRefreshToken()) {
        const refreshed = await refreshAccessToken();
        if (refreshed) {
            headers['Authorization'] = `Bearer ${getAccessToken()}`;
            return fetch(url, { ...options, headers });
        } else {
            clearTokens();
            window.location.href = 'login.html';
            return response;
        }
    }
    
    return response;
}

/**
 * FIX #1: Send refresh_token as JSON body (not query param)
 */
async function refreshAccessToken() {
    const refreshToken = getRefreshToken();
    if (!refreshToken) return false;
    
    try {
        const response = await fetch(`${AUTH_API_BASE}/auth/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: refreshToken })
        });
        
        if (response.ok) {
            const data = await response.json();
            // Keep same storage type (localStorage vs sessionStorage)
            if (localStorage.getItem('omniai_refresh_token')) {
                localStorage.setItem('omniai_access_token', data.access_token);
                if (data.refresh_token) {
                    localStorage.setItem('omniai_refresh_token', data.refresh_token);
                }
            } else {
                sessionStorage.setItem('omniai_access_token', data.access_token);
                if (data.refresh_token) {
                    sessionStorage.setItem('omniai_refresh_token', data.refresh_token);
                }
            }
            return true;
        }
    } catch (error) {
        console.error('Token refresh failed:', error);
    }
    
    return false;
}

// ============================================================================
// LOGIN (Step 56)
// ============================================================================

/**
 * FIX #4: Backend login returns {access_token, refresh_token} but NO user object.
 * So we fetch profile separately after login to get user info.
 */
async function login(email, password, rememberMe = false) {
    showLoading(true);
    hideError();
    
    try {
        const response = await fetch(`${AUTH_API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            storeTokens(data.access_token, data.refresh_token, rememberMe);
            
            // Fetch user profile (backend doesn't return user in login response)
            try {
                const profileRes = await fetch(`${AUTH_API_BASE}/auth/me`, {
                    headers: { 'Authorization': `Bearer ${data.access_token}` }
                });
                if (profileRes.ok) {
                    const user = await profileRes.json();
                    storeUser(user);
                }
            } catch (e) {
                // Non-critical - user info will load on next page
            }
            
            showSuccess('Login successful! Redirecting...');
            setTimeout(() => {
                window.location.href = 'index.html';
            }, 1000);
            
            return true;
        } else {
            showError(data.detail || 'Invalid email or password');
            return false;
        }
    } catch (error) {
        console.error('Login error:', error);
        showError('Connection failed. Please try again.');
        return false;
    } finally {
        showLoading(false);
    }
}

function loginWithGoogle() {
    window.location.href = `${AUTH_API_BASE}/auth/google`;
}

// ============================================================================
// SIGNUP (Step 57)
// ============================================================================

async function register(name, email, password) {
    showLoading(true);
    hideError();
    
    try {
        const response = await fetch(`${AUTH_API_BASE}/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, email, password })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            storeTokens(data.access_token, data.refresh_token, true);
            
            // Fetch profile after register
            try {
                const profileRes = await fetch(`${AUTH_API_BASE}/auth/me`, {
                    headers: { 'Authorization': `Bearer ${data.access_token}` }
                });
                if (profileRes.ok) {
                    const user = await profileRes.json();
                    storeUser(user);
                }
            } catch (e) { }
            
            showSuccess('Account created! Redirecting...');
            setTimeout(() => {
                window.location.href = 'index.html';
            }, 1000);
            
            return true;
        } else {
            if (response.status === 409) {
                showError('An account with this email already exists');
            } else if (response.status === 422) {
                showError(data.detail || 'Please check your input');
            } else {
                showError(data.detail || 'Registration failed');
            }
            return false;
        }
    } catch (error) {
        console.error('Registration error:', error);
        showError('Connection failed. Please try again.');
        return false;
    } finally {
        showLoading(false);
    }
}

function validatePassword(password) {
    const errors = [];
    if (password.length < 8) errors.push('At least 8 characters');
    if (!/[A-Z]/.test(password)) errors.push('One uppercase letter');
    if (!/[a-z]/.test(password)) errors.push('One lowercase letter');
    if (!/[0-9]/.test(password)) errors.push('One number');
    
    return {
        valid: errors.length === 0,
        errors,
        strength: calculatePasswordStrength(password)
    };
}

function calculatePasswordStrength(password) {
    let strength = 0;
    if (password.length >= 8) strength += 25;
    if (password.length >= 12) strength += 15;
    if (/[A-Z]/.test(password)) strength += 20;
    if (/[a-z]/.test(password)) strength += 15;
    if (/[0-9]/.test(password)) strength += 15;
    if (/[^A-Za-z0-9]/.test(password)) strength += 10;
    return Math.min(100, strength);
}

// ============================================================================
// PASSWORD RESET (Step 58)
// ============================================================================

/**
 * FIX #2: Send email as JSON body (not query param)
 */
async function forgotPassword(email) {
    showLoading(true);
    hideError();
    
    try {
        const response = await fetch(`${AUTH_API_BASE}/auth/forgot-password`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showSuccess(data.message || 'If an account exists, you will receive a reset email.');
            return data;
        } else {
            showSuccess('If an account exists, you will receive a reset email.');
            return null;
        }
    } catch (error) {
        console.error('Forgot password error:', error);
        showError('Connection failed. Please try again.');
        return null;
    } finally {
        showLoading(false);
    }
}

async function resetPassword(token, newPassword) {
    showLoading(true);
    hideError();
    
    try {
        const response = await fetch(`${AUTH_API_BASE}/auth/reset-password`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token, new_password: newPassword })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showSuccess('Password reset successful! Redirecting to login...');
            setTimeout(() => {
                window.location.href = 'login.html';
            }, 2000);
            return true;
        } else {
            showError(data.detail || 'Invalid or expired reset link');
            return false;
        }
    } catch (error) {
        console.error('Reset password error:', error);
        showError('Connection failed. Please try again.');
        return false;
    } finally {
        showLoading(false);
    }
}

// ============================================================================
// USER PROFILE (Step 59)
// ============================================================================

async function getProfile() {
    try {
        const response = await authFetch(`${AUTH_API_BASE}/auth/me`);
        if (response.ok) {
            const user = await response.json();
            storeUser(user);
            return user;
        }
        return null;
    } catch (error) {
        console.error('Get profile error:', error);
        return null;
    }
}

/**
 * FIX #6: Send name as JSON body (not query param)
 */
async function updateProfile(name) {
    showLoading(true);
    hideError();
    
    try {
        const response = await authFetch(`${AUTH_API_BASE}/auth/me`, {
            method: 'PUT',
            body: JSON.stringify({ name })
        });
        
        if (response.ok) {
            const result = await response.json();
            await getProfile();
            showSuccess('Profile updated!');
            return result;
        } else {
            const data = await response.json();
            showError(data.detail || 'Update failed');
            return null;
        }
    } catch (error) {
        console.error('Update profile error:', error);
        showError('Connection failed. Please try again.');
        return null;
    } finally {
        showLoading(false);
    }
}

/**
 * FIX #5: Correct URL (/auth/me/password) and method (PUT)
 */
async function changePassword(currentPassword, newPassword) {
    showLoading(true);
    hideError();
    
    try {
        const response = await authFetch(`${AUTH_API_BASE}/auth/me/password`, {
            method: 'PUT',
            body: JSON.stringify({
                current_password: currentPassword,
                new_password: newPassword
            })
        });
        
        if (response.ok) {
            showSuccess('Password changed successfully!');
            return true;
        } else {
            const data = await response.json();
            showError(data.detail || 'Password change failed');
            return false;
        }
    } catch (error) {
        console.error('Change password error:', error);
        showError('Connection failed. Please try again.');
        return false;
    } finally {
        showLoading(false);
    }
}

async function getPreferences() {
    try {
        const response = await authFetch(`${AUTH_API_BASE}/auth/me/preferences`);
        if (response.ok) return await response.json();
        return null;
    } catch (error) {
        console.error('Get preferences error:', error);
        return null;
    }
}

async function updatePreferences(preferences) {
    try {
        const response = await authFetch(`${AUTH_API_BASE}/auth/me/preferences`, {
            method: 'PUT',
            body: JSON.stringify(preferences)
        });
        if (response.ok) return await response.json();
        return null;
    } catch (error) {
        console.error('Update preferences error:', error);
        return null;
    }
}

// ============================================================================
// LOGOUT
// ============================================================================

/**
 * FIX #3: Removed call to non-existent /auth/logout endpoint.
 * Just clear tokens and redirect.
 */
function logout() {
    clearTokens();
    window.location.href = 'login.html';
}

// ============================================================================
// UI HELPERS
// ============================================================================

function showError(message) {
    const errorEl = document.getElementById('authError');
    const errorText = document.getElementById('errorText');
    if (errorEl && errorText) {
        errorText.textContent = message;
        errorEl.style.display = 'flex';
    }
    const successEl = document.getElementById('authSuccess');
    if (successEl) successEl.style.display = 'none';
}

function hideError() {
    const errorEl = document.getElementById('authError');
    if (errorEl) errorEl.style.display = 'none';
}

function showSuccess(message) {
    const successEl = document.getElementById('authSuccess');
    const successText = document.getElementById('successText');
    if (successEl && successText) {
        successText.textContent = message;
        successEl.style.display = 'flex';
    }
    hideError();
}

function showLoading(loading) {
    const submitBtn = document.getElementById('submitBtn');
    if (!submitBtn) return;
    
    const btnText = submitBtn.querySelector('.btn-text');
    const btnLoader = submitBtn.querySelector('.btn-loader');
    
    if (loading) {
        submitBtn.disabled = true;
        if (btnText) btnText.style.display = 'none';
        if (btnLoader) btnLoader.style.display = 'inline-flex';
    } else {
        submitBtn.disabled = false;
        if (btnText) btnText.style.display = 'inline';
        if (btnLoader) btnLoader.style.display = 'none';
    }
}

function togglePassword(inputId) {
    const input = document.getElementById(inputId);
    const icon = document.getElementById(inputId + 'ToggleIcon') || 
                 document.getElementById('passwordToggleIcon');
    
    if (input.type === 'password') {
        input.type = 'text';
        if (icon) icon.textContent = '🙈';
    } else {
        input.type = 'password';
        if (icon) icon.textContent = '👁️';
    }
}

function updatePasswordStrength(password) {
    const validation = validatePassword(password);
    const strengthBar = document.getElementById('passwordStrength');
    const strengthText = document.getElementById('passwordStrengthText');
    
    if (strengthBar) {
        strengthBar.style.width = validation.strength + '%';
        if (validation.strength < 40) {
            strengthBar.className = 'strength-bar weak';
        } else if (validation.strength < 70) {
            strengthBar.className = 'strength-bar medium';
        } else {
            strengthBar.className = 'strength-bar strong';
        }
    }
    
    if (strengthText) {
        if (validation.strength < 40) {
            strengthText.textContent = 'Weak';
            strengthText.className = 'strength-text weak';
        } else if (validation.strength < 70) {
            strengthText.textContent = 'Medium';
            strengthText.className = 'strength-text medium';
        } else {
            strengthText.textContent = 'Strong';
            strengthText.className = 'strength-text strong';
        }
    }
    
    return validation;
}

// ============================================================================
// AUTH CHECK (Step 61)
// ============================================================================

async function requireAuth() {
    if (!isAuthenticated()) {
        window.location.href = 'login.html';
        return false;
    }
    const user = await getProfile();
    if (!user) {
        clearTokens();
        window.location.href = 'login.html';
        return false;
    }
    return true;
}

function redirectIfLoggedIn() {
    if (isAuthenticated()) {
        window.location.href = 'index.html';
        return true;
    }
    return false;
}

// ============================================================================
// AUTO REFRESH (every 10 minutes)
// ============================================================================

setInterval(async () => {
    if (isAuthenticated()) {
        await refreshAccessToken();
    }
}, 10 * 60 * 1000);
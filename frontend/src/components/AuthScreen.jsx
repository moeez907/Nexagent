import React, { useState } from 'react';
import {
  Sparkles,
  Bot,
  Mail,
  Lock,
  Eye,
  EyeOff,
  User,
  ShieldCheck,
  Check,
  ArrowRight,
  X,
  Cpu,
  Globe
} from 'lucide-react';
import { login, signup } from '../services/api';

export default function AuthScreen({ onAuthenticated, onClose }) {
  const [mode, setMode] = useState('login'); // 'login' | 'signup'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [rememberDevice, setRememberDevice] = useState(true);
  const [agreeTerms, setAgreeTerms] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  // Password strength calculation (0-4)
  const getPasswordStrength = (pass) => {
    if (!pass) return 0;
    let score = 0;
    if (pass.length >= 8) score++;
    if (/[A-Z]/.test(pass) && /[a-z]/.test(pass)) score++;
    if (/[0-9]/.test(pass)) score++;
    if (/[^A-Za-z0-9]/.test(pass) || pass.length >= 12) score++;
    return score;
  };

  const passStrength = getPasswordStrength(password);
  const strengthLabels = ['', 'Weak', 'Fair', 'Good', 'Strong'];

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');

    if (mode === 'signup' && !agreeTerms) {
      setError('Please agree to the Terms of Service and Privacy Policy to continue.');
      setBusy(false);
      return;
    }

    try {
      const account = mode === 'login' ? await login(email, password) : await signup(email, password, fullName);
      onAuthenticated(account);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-page-wrapper">
      {/* Top Header Logo */}
      <header className="auth-top-header">
        <div className="auth-brand-lockup">
          <img src="/logo.png" alt="Nexagent" className="auth-brand-img" />
          <span className="auth-brand-name">
            Nex<span className="auth-brand-gradient">agent</span>
          </span>
        </div>
      </header>

      {/* Pill Badge Above Card */}
      <div className="auth-cluster-pill">
        <span className="cluster-dot" />
        {mode === 'login' ? (
          <span>AI WEB AGENT WORKSPACE</span>
        ) : (
          <span>CREATE YOUR ACCOUNT</span>
        )}
      </div>

      {/* Main Authentication Card */}
      <div className="auth-card-container">
        {onClose && (
          <button
            type="button"
            className="auth-close-btn"
            onClick={onClose}
            title="Return to Home"
          >
            <X size={16} />
          </button>
        )}

        {/* Card Header */}
        <div className="auth-card-header">
          {mode === 'login' ? (
            <>
              <img src="/logo.png" alt="Nexagent" className="auth-card-logo-img" />
              <div className="auth-badge-workspace">
                NEXAGENT
              </div>
              <h1 className="auth-title">Welcome back</h1>
              <p className="auth-subtitle">
                Sign in to your account to run web agent tasks and view your task history.
              </p>
            </>
          ) : (
            <>
              <img src="/logo.png" alt="Nexagent" className="auth-card-logo-img" />
              <h1 className="auth-title">Create your Nexagent account</h1>
              <p className="auth-subtitle">
                Run autonomous web tasks, extract live web data, and inspect browser sessions.
              </p>
            </>
          )}
        </div>

        {/* Form Body */}
        <form className="auth-form-modern" onSubmit={submit}>
          {/* Full Name (Sign Up only) */}
          {mode === 'signup' && (
            <div className="auth-field-group">
              <label className="auth-label">Full Name</label>
              <div className="auth-input-wrapper">
                <User size={15} className="input-icon-left" />
                <input
                  type="text"
                  placeholder="Your Name"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="auth-input-field"
                  autoComplete="name"
                />
              </div>
            </div>
          )}

          {/* Email */}
          <div className="auth-field-group">
            <div className="auth-label-row">
              <label className="auth-label">Email</label>
            </div>
            <div className="auth-input-wrapper">
              <Mail size={15} className="input-icon-left" />
              <input
                type="email"
                placeholder="name@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="auth-input-field"
                autoComplete="email"
              />
            </div>
          </div>

          {/* Password */}
          <div className="auth-field-group">
            <div className="auth-label-row">
              <label className="auth-label">Password</label>
              {mode === 'signup' && (
                <span className={`auth-strength-text strength-${passStrength}`}>
                  {strengthLabels[passStrength] || 'Minimum 8 chars'}
                </span>
              )}
            </div>
            <div className="auth-input-wrapper">
              <Lock size={15} className="input-icon-left" />
              <input
                type={showPassword ? 'text' : 'password'}
                placeholder="••••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                className="auth-input-field"
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              />
              <button
                type="button"
                className="input-eye-toggle"
                onClick={() => setShowPassword(!showPassword)}
                tabIndex={-1}
              >
                {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>

            {/* Password strength meter for Signup */}
            {mode === 'signup' && (
              <div className="password-meter-bars">
                <span className={`meter-seg ${passStrength >= 1 ? 'filled filled-weak' : ''}`} />
                <span className={`meter-seg ${passStrength >= 2 ? 'filled filled-fair' : ''}`} />
                <span className={`meter-seg ${passStrength >= 3 ? 'filled filled-good' : ''}`} />
                <span className={`meter-seg ${passStrength >= 4 ? 'filled filled-strong' : ''}`} />
              </div>
            )}
          </div>

          {/* Checkboxes: Remember device (Login) OR Terms Agreement (Signup) */}
          {mode === 'login' ? (
            <div className="auth-checkbox-row">
              <label className="auth-checkbox-label">
                <input
                  type="checkbox"
                  checked={rememberDevice}
                  onChange={(e) => setRememberDevice(e.target.checked)}
                  className="auth-checkbox"
                />
                <span>Remember this device</span>
              </label>
            </div>
          ) : (
            <div className="auth-terms-row">
              <input
                type="checkbox"
                id="agree-terms"
                checked={agreeTerms}
                onChange={(e) => setAgreeTerms(e.target.checked)}
                className="auth-checkbox"
                required
              />
              <label htmlFor="agree-terms" className="auth-terms-text">
                I agree to the <a href="#terms" onClick={(e) => e.preventDefault()}>Terms of Service</a> and{' '}
                <a href="#privacy" onClick={(e) => e.preventDefault()}>Privacy Policy</a>.
              </label>
            </div>
          )}

          {/* Error Banner */}
          {error && <div className="auth-error-banner">{error}</div>}

          {/* Primary Submit Button */}
          <button type="submit" className="auth-btn-primary" disabled={busy}>
            <span>
              {busy
                ? 'Validating credentials...'
                : mode === 'login'
                ? 'Sign In to Workspace'
                : 'Create Account'}
            </span>
            <ArrowRight size={16} />
          </button>


          {/* Switch Mode Link */}
          <div className="auth-switch-footer">
            {mode === 'login' ? (
              <span>
                New to Nexagent?{' '}
                <button
                  type="button"
                  className="switch-link"
                  onClick={() => {
                    setMode('signup');
                    setError('');
                  }}
                >
                  Create an account
                </button>
              </span>
            ) : (
              <span>
                Already have an account?{' '}
                <button
                  type="button"
                  className="switch-link"
                  onClick={() => {
                    setMode('login');
                    setError('');
                  }}
                >
                  Log in
                </button>
              </span>
            )}
          </div>

          {/* Sign Up Features Real Trust */}
          {mode === 'signup' && (
            <div className="signup-features-row">
              <span>
                <Check size={12} color="#10b981" /> Live Browser Navigation
              </span>
              <span>•</span>
              <span>
                <Check size={12} color="#2563eb" /> DOM &amp; Vision Reasoning
              </span>
              <span>•</span>
              <span>
                <Check size={12} color="#7c3aed" /> Structured Data Extraction
              </span>
            </div>
          )}
        </form>
      </div>

      {/* Trust Badges Below Card */}
      <div className="auth-security-pills-row">
        <div className="sec-pill">
          <ShieldCheck size={13} color="#2563eb" />
          <span>Secure Web Agent Workspace</span>
        </div>
        <div className="sec-pill">
          <Globe size={13} color="#059669" />
          <span>Live Browser Viewport</span>
        </div>
        <div className="sec-pill">
          <Cpu size={13} color="#475569" />
          <span>Playwright &amp; AI Driven</span>
        </div>
      </div>

      {/* Footer Links */}
      <footer className="auth-footer-links">
        <a href="#terms" onClick={(e) => e.preventDefault()}>Terms</a>
        <span>•</span>
        <a href="#privacy" onClick={(e) => e.preventDefault()}>Privacy</a>
        <span>•</span>
        <a href="#status" onClick={(e) => e.preventDefault()}>Status</a>
      </footer>
    </div>
  );
}

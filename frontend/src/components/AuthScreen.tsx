import { useState } from 'react'

import type { UserRole } from '../lib/types'

interface AuthScreenProps {
  error: string
  onSignIn: (email: string, password: string) => void
  onCreateAccount: (payload: { name: string; email: string; password: string; role: UserRole }) => void
}

export function AuthScreen({ error, onSignIn, onCreateAccount }: AuthScreenProps) {
  const [mode, setMode] = useState<'signin' | 'signup'>('signin')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('alex@polyclaw.local')
  const [password, setPassword] = useState('demo1234')
  const [role, setRole] = useState<UserRole>('trader')

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (mode === 'signin') {
      onSignIn(email, password)
      return
    }

    onCreateAccount({ name, email, password, role })
  }

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <div className="auth-card__intro">
          <p className="eyebrow">PolyClaw Internal Desk</p>
          <h1>Decision dashboard for live and paper Polymarket workflows</h1>
          <p className="muted">
            Prototype auth is stored locally for now, so the frontend can support named users before the backend auth
            service is ready.
          </p>
        </div>

        <div className="auth-toggle">
          <button
            className={`button ${mode === 'signin' ? 'button--primary' : 'button--ghost'}`}
            type="button"
            onClick={() => setMode('signin')}
          >
            Sign in
          </button>
          <button
            className={`button ${mode === 'signup' ? 'button--primary' : 'button--ghost'}`}
            type="button"
            onClick={() => setMode('signup')}
          >
            Create account
          </button>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          {mode === 'signup' ? (
            <label>
              Name
              <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Jordan Smith" />
            </label>
          ) : null}

          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="name@polyclaw.local"
            />
          </label>

          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Enter your password"
            />
          </label>

          {mode === 'signup' ? (
            <label>
              Role
              <select value={role} onChange={(event) => setRole(event.target.value as UserRole)}>
                <option value="trader">Trader</option>
                <option value="analyst">Analyst</option>
                <option value="operator">Operator</option>
              </select>
            </label>
          ) : null}

          {error ? <p className="form-error">{error}</p> : null}

          <button className="button button--primary auth-form__submit" type="submit">
            {mode === 'signin' ? 'Enter dashboard' : 'Create prototype account'}
          </button>
        </form>

        <div className="auth-card__footer">
          <p className="muted">Seed login for the prototype: `alex@polyclaw.local` / `demo1234`</p>
        </div>
      </section>
    </main>
  )
}

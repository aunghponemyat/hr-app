import { Link } from 'react-router-dom'

export function FeaturePlaceholder({ title }: { title: string }) {
  return (
    <section className="card">
      <p className="eyebrow">Your workspace</p>
      <h1>{title}</h1>
      <p className="muted">
        This page is being prepared. Your account is signed in and ready.
      </p>
      {title === 'Profile' && (
        <Link to="/change-password">Change password</Link>
      )}
    </section>
  )
}

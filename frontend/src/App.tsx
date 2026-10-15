import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from './auth/AuthProvider'
import { AuthSession } from './auth/session'
import { AppRoutes } from './routes'

const session = new AuthSession()

function App() {
  return (
    <AuthProvider session={session}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App

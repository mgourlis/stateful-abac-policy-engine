import { Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from './components/Layout'
import { RealmList } from './pages/RealmList'
import { RealmDetail } from './pages/RealmDetail'

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Navigate to="/realms" replace />} />
        <Route path="realms" element={<RealmList />} />
        <Route path="realms/:realmId/*" element={<RealmDetail />} />
      </Route>
    </Routes>
  )
}

export default App

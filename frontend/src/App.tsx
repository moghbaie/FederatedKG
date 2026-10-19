import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import { Layout } from "./Layout";
import { Audit } from "./pages/Audit";
import { Channels } from "./pages/Channels";
import { Directory } from "./pages/Directory";
import { Discover } from "./pages/Discover";
import { Login } from "./pages/Login";
import { Matches } from "./pages/Matches";
import { Requests } from "./pages/Requests";

// The graph view pulls in Cytoscape; load it only when opened.
const MyKG = lazy(() => import("./pages/MyKG").then((m) => ({ default: m.MyKG })));

export function App() {
  const { me, loading } = useAuth();
  if (loading) return <p className="content muted">Loading…</p>;
  if (!me) {
    return (
      <Routes>
        <Route path="*" element={<Login />} />
      </Routes>
    );
  }
  const home = me.verified_researcher ? "/discover" : "/audit";
  const verifiedOnly = (el: JSX.Element) => (me.verified_researcher ? el : <Navigate to="/audit" replace />);
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/kg" element={verifiedOnly(<Suspense fallback={<p className="muted">Loading graph…</p>}><MyKG /></Suspense>)} />
        <Route path="/directory" element={verifiedOnly(<Directory />)} />
        <Route path="/discover" element={verifiedOnly(<Discover />)} />
        <Route path="/channels" element={verifiedOnly(<Channels />)} />
        <Route path="/requests" element={verifiedOnly(<Requests />)} />
        <Route path="/matches" element={verifiedOnly(<Matches />)} />
        <Route path="/audit" element={<Audit />} />
        <Route path="*" element={<Navigate to={home} replace />} />
      </Route>
    </Routes>
  );
}

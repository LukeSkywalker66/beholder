import { useState } from "react";
import SearchBox from "./components/SearchBox";
import OutputBox from "./components/OutputBox";
import './App.css';
import logo from './assets/beholder2.png';

function App() {
  const [resultData, setResultData] = useState<any>(null);

  return (
    <div className="layout">
      {/* Panel izquierdo */}
      <aside className="sidebar">
        <img src={logo} alt="Logo Beholder" className="logo-sidebar" />
        <h1>Beholder</h1>
        <h2>Diagnóstico centralizado de 2F Internet</h2>
        <SearchBox onResult={setResultData} />
      </aside>

      {/* Panel derecho */}
      <main className="results">
        {resultData && <OutputBox data={resultData} />}
      </main>
    </div>
  );
}

export default App;

import CopyButton from "./CopyButton";

interface OutputBoxProps {
  data: any;
}

export default function OutputBox({ data }: OutputBoxProps) {
  const traducciones: Record<string, string> = {
    Online: "En línea",
    "Power fail": "Problema de energía",
    LOS: "Sin señal/sin luz",
    Offline: "Fuera de línea",
    true: "Conectado",
    false: "Desconectado",
    Critical: "Crítico - Luz muy alta",
    Warning: "Advertencia - Luz alta",
    "Very good": "Muy buena - Luz óptima",
  };

  // Texto plano para copiar
  const outputText = `
    Cliente: ${data?.cliente_nombre ?? "-"}
    Domicilio: ${data?.direccion ?? "-"}
    Plan: ${data?.plan ?? "-"}
    Nodo: ${data?.nodo_nombre ? data.nodo_nombre + " - " + (data?.nodo_ip ?? "-") : "-"}
    OLT: ${data?.OLT ?? "-"}
    PPPoE User: ${data?.pppoe_username ?? "-"}
    Estado PPPoE: ${traducciones[data?.mikrotik?.active] ?? "-"}
    Tiempo activo: ${data?.mikrotik?.uptime ?? "-"}
    Última conexión: ${data?.mikrotik?.secret?.["last-logged-out"] ?? "-"}
    ONU s/n: ${data?.onu_sn ?? "-"}
    ONU Estado: ${traducciones[data?.onu_status_smrt?.onu_status] ?? "-"}
    ONU Último cambio de estado: ${data?.onu_status_smrt?.last_status_change ?? "-"}
    ONU Señal: ${traducciones[data?.onu_signal_smrt?.onu_signal] ?? "-"}
    ONU Señal Detalle: ${data?.onu_signal_smrt?.onu_signal_value ?? "-"}
    `;

  return (
    <div className="border rounded p-4 mt-4 bg-gray-50">
      <div className="header-row">
        <h3 className="diagnostic-title">Diagnóstico normalizado</h3>
        <CopyButton text={outputText} />
      </div>
      <div className="bg-white p-2 rounded font-mono whitespace-pre-wrap">
      <div className="grid">
        <div className="cell span-2"><strong>Cliente:</strong> {data?.cliente_nombre ?? "-"}</div>
        <div className="cell span-2"><strong>Domicilio:</strong> {data?.direccion ?? "-"}</div>
        <div className="cell"><strong>Plan:</strong> {data?.plan ?? "-"}</div>
        <div className="cell"><strong>Nodo:</strong> {data?.nodo_nombre ? data.nodo_nombre + " - " + (data?.nodo_ip ?? "-") : "-"}</div>
        <div className="cell"><strong>OLT:</strong> {data?.OLT ?? "-"}</div>
        <div className={`cell ${data?.mikrotik?.active ? "estado-ok" : "estado-error"}`}>
          <strong>Estado PPPoE:</strong> {traducciones[data?.mikrotik?.active] ?? "-"}
        </div>
        <div className="cell"><strong>Tiempo activo:</strong> {data?.mikrotik?.uptime ?? "-"}</div>
        <div className="cell"><strong>Última conexión:</strong> {data?.mikrotik?.secret?.["last-logged-out"] ?? "-"}</div>
        <div className="cell"><strong>ONU s/n:</strong> {data?.onu_sn ?? "-"}</div>
        <div className={`cell ${data?.onu_status_smrt?.onu_status === "Online" ? "estado-ok" : "estado-error"}`}>
          <strong>ONU Estado:</strong> {traducciones[data?.onu_status_smrt?.onu_status] ?? "-"}
        </div>
        <div className="cell"><strong>Último cambio de estado:</strong> {data?.onu_status_smrt?.last_status_change ?? "-"}</div>
        <div className="cell"><strong>ONU Señal:</strong> {traducciones[data?.onu_signal_smrt?.onu_signal] ?? "-"}</div>
        <div className="cell"><strong>Señal Detalle:</strong> {data?.onu_signal_smrt?.onu_signal_value ?? "-"}</div>
        </div>
        
      </div>
      <CopyButton text={outputText} />
    </div>
    //luego agregar los demas campos de datos de cliente
  );
}
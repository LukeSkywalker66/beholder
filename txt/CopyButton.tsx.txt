import { useState } from "react";

interface CopyButtonProps {
  text: string; // el texto que querés copiar
}

export default function CopyButton({ text }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  const copyToClipboard = async () => {
    console.log("Click detectado, texto:", text);
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        // ✅ Camino moderno (HTTPS / localhost)
        await navigator.clipboard.writeText(text);
        console.log("Camino moderno (HTTPS / localhost) usado para copiar al portapapeles.");
      } else {
        // ✅ Fallback para HTTP inseguro
        const textarea = document.createElement("textarea");
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
        console.log("Fallback usado para copiar al portapapeles.");
      }

      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Error copiando al portapapeles", err);
    }
  };


  return (
    <div className="copy-button">
      <button onClick={copyToClipboard}>
        📋 Copiar
      </button>
      {copied && <span style={{ marginLeft: "8px" }}>✔ Copiado</span>}
    </div>
  );

}
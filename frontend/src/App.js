import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import Terminal from "@/pages/Terminal";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Terminal />} />
      </Routes>
      <Toaster
        theme="dark"
        position="bottom-right"
        toastOptions={{
          classNames: {
            toast: "!bg-[#121212] !border-[#27272A] !text-white !rounded-sm font-mono text-xs",
            warning: "!border-[#FB923C]/60",
          },
        }}
      />
    </BrowserRouter>
  );
}

export default App;

import { useCallback, useEffect, useRef, useState } from "react";

type Job = { id:string; filename:string; operation:string; status:string; attempt_count:number; error_message:string|null; created_at:string };
const API = "/api/v1";

export default function App() {
  const [token, setToken] = useState(localStorage.getItem("cloudflow_token") || "");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [register, setRegister] = useState(false);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [operation, setOperation] = useState("resize");
  const [width, setWidth] = useState("1200");
  const [height, setHeight] = useState("");
  const [quality, setQuality] = useState("75");
  const [user, setUser] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const picker = useRef<HTMLInputElement>(null);

  const call = useCallback(async (path:string, init:RequestInit={}) => {
    const response = await fetch(path, {...init, headers:{Authorization:"Bearer "+token, ...init.headers}});
    if (response.status === 401) {
      localStorage.removeItem("cloudflow_token"); setToken(""); throw new Error("Session expired. Sign in again.");
    }
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || "Request failed ("+response.status+")");
    }
    return response.json();
  }, [token]);

  const refresh = useCallback(async () => {
    if (!token) return;
    try { setJobs(await call(API+"/jobs")); } catch (e) { setError(e instanceof Error ? e.message : "Unable to load jobs"); }
  }, [token, call]);

  useEffect(() => {
    if (!token) return;
    void call(API+"/auth/me").then((data) => setUser(data.email)).catch(() => undefined);
    void refresh();
    const timer = window.setInterval(() => void refresh(), 3000);
    return () => window.clearInterval(timer);
  }, [token, call, refresh]);

  async function auth(event:React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const data = await call(API+"/auth/"+(register ? "register" : "login"), {
        method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({email,password})
      });
      localStorage.setItem("cloudflow_token", data.access_token); setToken(data.access_token); setUser(data.user.email);
    } catch(e) { setError(e instanceof Error ? e.message : "Authentication failed"); }
    finally { setBusy(false); }
  }

  function choose(selected:FileList|File[]) {
    const list = Array.from(selected);
    const images = list.filter((f) => f.type.startsWith("image/"));
    setFiles(images);
    setError(images.length !== list.length ? "Choose image files only." : "");
  }

  async function upload(event:React.FormEvent) {
    event.preventDefault();
    if (!files.length) { setError("Choose at least one image."); return; }
    setBusy(true); setError("");
    const spec:{name:string;width?:number;height?:number;quality?:number} = {name:operation};
    if (operation === "resize") { spec.width = Number(width) || undefined; spec.height = Number(height) || undefined; }
    if (operation === "compress") spec.quality = Number(quality);
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    form.append("operation", JSON.stringify(spec));
    try { const data = await call(API+"/jobs", {method:"POST", body:form}); setJobs((old) => [...data.jobs,...old]); setFiles([]); if(picker.current) picker.current.value=""; }
    catch(e) { setError(e instanceof Error ? e.message : "Upload failed"); }
    finally { setBusy(false); }
  }

  async function retry(id:string) {
    try { await call(API+"/jobs/"+id+"/retry", {method:"POST"}); await refresh(); }
    catch(e) { setError(e instanceof Error ? e.message : "Retry failed"); }
  }

  async function download(id:string) {
    try { const data = await call(API+"/jobs/"+id+"/download"); window.location.assign(data.url); }
    catch(e) { setError(e instanceof Error ? e.message : "Download failed"); }
  }

  function logout() { localStorage.removeItem("cloudflow_token"); setToken(""); setJobs([]); setUser(""); }

  if (!token) return <main className="auth-shell"><section className="auth-card">
    <Brand/><p className="eyebrow">CLOUD IMAGE WORKSPACE</p>
    <h1>{register ? "Create your account" : "Welcome back"}</h1>
    <p className="muted">Process images with a reliable cloud queue.</p>
    <form className="stack" onSubmit={auth}>
      <label>Email<input required type="email" autoComplete="email" value={email} onChange={(e)=>setEmail(e.target.value)}/></label>
      <label>Password<input required minLength={10} type="password" autoComplete={register?"new-password":"current-password"} value={password} onChange={(e)=>setPassword(e.target.value)}/></label>
      {error && <p className="alert" role="alert">{error}</p>}
      <button className="primary" disabled={busy}>{busy?"Working…":register?"Create account":"Sign in"} <span>→</span></button>
    </form>
    <button className="text-button" onClick={()=>{setRegister(!register);setError("");}}>{register?"Already registered? Sign in":"New to CloudFlow? Create an account"}</button>
    <p className="fine-print">Your files stay private and are available only to your account.</p>
  </section></main>;

  const active = jobs.filter((j)=>j.status==="QUEUED"||j.status==="PROCESSING").length;
  const complete = jobs.filter((j)=>j.status==="COMPLETED").length;
  return <div className="app-shell">
    <aside className="sidebar"><Brand/><p className="nav-label">WORKSPACE</p><div className="nav-item active">▦ &nbsp; Image jobs</div>
      <div className="side-note"><i/> Asynchronous processing</div>
      <div className="sidebar-bottom"><div className="avatar">{user.slice(0,1).toUpperCase()}</div><div className="user-copy"><b>{user}</b><small>Personal workspace</small></div><button className="icon-button" onClick={logout} aria-label="Sign out">↗</button></div>
    </aside>
    <main className="main"><header className="topbar"><span>Workspace <b>/</b> Image jobs</span><button className="profile" onClick={logout}>Sign out</button></header>
      <div className="content">
        <div className="page-heading"><div><p className="eyebrow">YOUR WORKSPACE</p><h1>Image operations</h1><p className="muted">Upload, process, and manage your image jobs in one place.</p></div><span className="region-chip"><i/> Mumbai · ap-south-1</span></div>
        <section className="stats"><Stat label="Jobs shown" value={jobs.length} icon="▤"/><Stat label="In progress" value={active} icon="◷"/><Stat label="Completed" value={complete} icon="✓"/></section>
        <section className="panel upload-panel"><div className="section-title"><div><p className="eyebrow">NEW PROCESSING JOB</p><h2>Upload images</h2></div><span className="step">01 <i>/</i> 02</span></div>
          <form onSubmit={upload}>
            <div className={"dropzone "+(dragging?"dragging":"")} onDragOver={(e)=>{e.preventDefault();setDragging(true);}} onDragLeave={()=>setDragging(false)} onDrop={(e)=>{e.preventDefault();setDragging(false);choose(e.dataTransfer.files);}}>
              <input ref={picker} type="file" multiple accept="image/jpeg,image/png,image/webp" onChange={(e)=>e.target.files&&choose(e.target.files)}/>
              <div className="upload-icon">↑</div><strong>Drop your images here</strong><span>or <button type="button" className="inline-link" onClick={()=>picker.current?.click()}>browse files</button> from your computer</span><small>JPG, PNG, WebP · Up to 10 MB each</small>
              {files.length>0&&<div className="file-summary">{files.length} image(s) selected: {files.map((f)=>f.name).join(", ")}</div>}
            </div>
            <div className="form-row"><label>Operation<select value={operation} onChange={(e)=>setOperation(e.target.value)}>
              <option value="resize">Resize image</option><option value="compress">Compress image</option><option value="jpeg_to_png">JPEG to PNG</option><option value="png_to_jpeg">PNG to JPEG</option><option value="grayscale">Grayscale</option>
            </select></label>
            {operation==="resize"&&<div className="option-pair"><label>Max width (px)<input type="number" min="1" max="5000" value={width} onChange={(e)=>setWidth(e.target.value)}/></label><label>Max height (px)<input type="number" min="1" max="5000" placeholder="Keep ratio" value={height} onChange={(e)=>setHeight(e.target.value)}/></label></div>}
            {operation==="compress"&&<label>Quality: {quality}%<input type="range" min="10" max="95" value={quality} onChange={(e)=>setQuality(e.target.value)}/></label>}
            <div className="form-action"><button className="primary" disabled={busy||!files.length}>{busy?"Queuing…":"Start processing"} <span>→</span></button></div></div>
          </form>
          {error&&<p className="alert" role="alert">{error}</p>}
          <p className="privacy">◈ &nbsp; Files are stored in your private workspace.</p>
        </section>
        <section className="jobs-section"><div className="section-title"><div><p className="eyebrow">ACTIVITY</p><h2>Recent jobs <span className="count">{jobs.length}</span></h2></div><button className="refresh" onClick={()=>void refresh()}>↻ Refresh</button></div>
          <div className="jobs-table"><div className="table-head"><span>FILE</span><span>OPERATION</span><span>STATUS</span><span>CREATED</span><span>ACTION</span></div>
            {jobs.length===0?<div className="empty"><div className="empty-icon">▤</div><strong>No jobs yet</strong><span>Your processed images will appear here.</span></div>:
            jobs.map((job)=><JobRow key={job.id} job={job} onRetry={()=>void retry(job.id)} onDownload={()=>void download(job.id)}/>)}
          </div>
        </section>
        <footer>CloudFlow <span>·</span> Asynchronous image processing on AWS</footer>
      </div>
    </main>
  </div>;
}

function Brand(){return <div className="brand"><div className="brand-mark">C</div><span>cloudflow<span className="brand-dot">.</span></span></div>;}
function Stat({label,value,icon}:{label:string;value:number;icon:string}){return <div className="stat-card"><div className="stat-icon">{icon}</div><div><span>{label}</span><strong>{value.toString().padStart(2,"0")}</strong></div><div className="stat-bar"/></div>;}
function JobRow({job,onRetry,onDownload}:{job:Job;onRetry:()=>void;onDownload:()=>void}){
  const operation=job.operation.replaceAll("_"," ").replace(/\b\w/g,(c)=>c.toUpperCase());
  return <div className="job-row"><div className="file-cell"><div className="file-icon">▧</div><div><strong>{job.filename}</strong><small>{job.id.slice(0,8)}</small></div></div><span className="operation-label">{operation}</span><span className={"status "+job.status.toLowerCase()}><i/>{job.status.toLowerCase()}</span><span className="created">{new Date(job.created_at).toLocaleString()}</span><div className="actions">{job.status==="COMPLETED"?<button className="download" onClick={onDownload}>Download ↓</button>:job.status==="FAILED"?<button className="retry" onClick={onRetry}>Retry ↻</button>:<span className="waiting">—</span>}</div>{job.error_message&&<div className="job-error">{job.error_message}</div>}</div>;
}


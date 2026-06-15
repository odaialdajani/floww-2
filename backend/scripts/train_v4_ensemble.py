#!/usr/bin/env python3
"""V4 Ensemble ML training pipeline — 80+ features, Sharpe-optimized selection."""
from __future__ import annotations
import argparse, json, logging, sys, time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import numpy as np, pandas as pd, yfinance as yf

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("train_v4")
UP_THRESHOLD, DOWN_THRESHOLD = 0.003, -0.003

def compute_features(ticker, period="5y"):
    data = yf.download(ticker, period=period, progress=False)
    if data.empty: raise ValueError(f"No data for {ticker}")
    if isinstance(data.columns, pd.MultiIndex): data.columns = data.columns.get_level_values(0)
    df = data.copy().dropna(subset=["Close"])
    c = df["Close"].astype(float)
    h = df["High"].astype(float) if "High" in df.columns else c
    l = df["Low"].astype(float) if "Low" in df.columns else c
    v = df["Volume"].astype(float) if "Volume" in df.columns else pd.Series(1.0, index=df.index)
    o = df["Open"].astype(float) if "Open" in df.columns else c
    F = pd.DataFrame(index=df.index)
    for hor, name in [(1,"ret_1d"),(2,"ret_2d"),(3,"ret_3d"),(5,"ret_5d"),(10,"ret_10d"),(21,"ret_21d")]:
        F[name] = c.pct_change(hor)
    lr = np.log(c/c.shift(1))
    F["log_ret_1d"] = lr
    F["overnight_gap"] = o/c.shift(1)-1.0
    for w in [5,10,21,30,42,50,200]:
        s = c.rolling(w,min_periods=w).mean()
        F[f"sma_{w}"] = s; F[f"price_vs_sma_{w}"] = c/s-1.0
    for sp in [12,26,50,200]:
        e = c.ewm(span=sp,adjust=False).mean()
        F[f"ema_{sp}"] = e; F[f"price_vs_ema_{sp}"] = c/e-1.0
    for fast,slow in [(5,21),(10,50),(21,50),(50,200)]:
        fs,ss = c.rolling(fast,min_periods=fast).mean(), c.rolling(slow,min_periods=slow).mean()
        F[f"sma_{fast}_{slow}_diff"] = fs-ss; F[f"sma_{fast}_{slow}_cross"] = np.sign(fs-ss)
    for w in [7,14,21]:
        tr = pd.concat([h-l,(h-c.shift(1)).abs(),(l-c.shift(1)).abs()],axis=1).max(axis=1)
        F[f"atr_{w}"] = tr.rolling(w,min_periods=w).mean()
        F[f"atr_{w}_pct"] = F[f"atr_{w}"]/c
    for w in [5,10,21,60]: F[f"volume_sma_{w}"] = v.rolling(w,min_periods=w).mean()
    F["relative_volume"] = v/(F["volume_sma_21"]+1e-10)
    F["vol_ratio_5_21"] = F["volume_sma_5"]/(F["volume_sma_21"]+1e-10)
    F["vol_ratio_5_60"] = F["volume_sma_5"]/(F["volume_sma_60"]+1e-10)
    for w in [3,5,10,15,21,42,60]:
        F[f"realized_vol_{w}d"] = lr.rolling(w,min_periods=w).std()*np.sqrt(252)
    F["vol_of_vol"] = F["realized_vol_21d"].rolling(21,min_periods=21).std()
    F["vol_spike"] = F["realized_vol_5d"]/(F["realized_vol_21d"]+1e-10)
    F["vol_regime"] = (F["realized_vol_21d"]>F["realized_vol_21d"].rolling(60,min_periods=60).mean()).astype(float)
    for w in [7,14,21]:
        d=c.diff(); g=d.where(d>0,0.0).rolling(w,min_periods=w).mean(); lo=(-d.where(d<0,0.0)).rolling(w,min_periods=w).mean()
        rs=g/(lo+1e-10); F[f"rsi_{w}"] = 100-(100/(1+rs))
    F["rsi_overbought"] = (F["rsi_14"]>70).astype(float)
    F["rsi_oversold"] = (F["rsi_14"]<30).astype(float)
    e12,e26 = c.ewm(span=12,adjust=False).mean(), c.ewm(span=26,adjust=False).mean()
    macd = e12-e26; macd_s = macd.ewm(span=9,adjust=False).mean()
    F["macd"], F["macd_signal"], F["macd_hist"] = macd, macd_s, macd-macd_s
    for w in [20,50]:
        s=c.rolling(w,min_periods=w).mean(); sd=c.rolling(w,min_periods=w).std()
        F[f"bb_upper_{w}"] = s+2*sd; F[f"bb_lower_{w}"] = s-2*sd
        F[f"bb_position_{w}"] = (c-F[f"bb_lower_{w}"])/(F[f"bb_upper_{w}"]-F[f"bb_lower_{w}"]+1e-10)
    lw14=l.rolling(14,min_periods=14).min(); hw14=h.rolling(14,min_periods=14).max()
    F["stochastic_k"] = 100*(c-lw14)/(hw14-lw14+1e-10)
    F["stochastic_d"] = F["stochastic_k"].rolling(3,min_periods=3).mean()
    F["williams_r"] = -100*(hw14-c)/(hw14-lw14+1e-10)
    tp=(h+l+c)/3; F["cci_20"] = (tp-tp.rolling(20,min_periods=20).mean())/(0.015*tp.rolling(20,min_periods=20).std()+1e-10)
    F["ret_momentum_5"] = c.pct_change(5); F["ret_accel_5"] = c.pct_change(5).diff()
    F["distance_from_21sma"] = (c-F["sma_21"])/(F["atr_14"]+1e-10)
    dt = pd.to_datetime(F.index)
    F["day_of_week"] = dt.dayofweek.astype(float)
    F["month"] = dt.month.astype(float)
    F["is_month_end"] = dt.is_month_end.astype(float)
    F["is_month_start"] = dt.is_month_start.astype(float)
    F["is_quarter_end"] = dt.is_quarter_end.astype(float)
    F["trend_direction_21"] = np.sign(c-c.shift(21))
    F["consecutive_up"] = (c>c.shift(1)).astype(float).rolling(5,min_periods=1).sum()
    nxt = c.pct_change(1).shift(-1)
    tgt = pd.Series(1,index=df.index,dtype=int)
    tgt = tgt.where(~nxt.gt(UP_THRESHOLD),2).where(~nxt.lt(DOWN_THRESHOLD),0)
    F["target_3class"] = tgt
    F = F.replace([np.inf,-np.inf],np.nan).fillna(0.0)
    log.info("Computed %d features for %s (%d rows)", len(F.columns)-1, ticker, len(F))
    return F

def compute_sharpe(yt,yp):
    pnl=[]
    for i in range(len(yt)):
        if yp[i]==2: pnl.append(1.0 if yt[i]==2 else (-1.0 if yt[i]==0 else 0.0))
        elif yp[i]==0: pnl.append(1.0 if yt[i]==0 else (-1.0 if yt[i]==2 else 0.0))
    if len(pnl)<5: return 0.0
    a=np.array(pnl); return float(a.mean()/(a.std()+1e-10)*np.sqrt(252))

def walk_forward_cv(model,X,y,n_splits=5,embargo=5):
    from sklearn.metrics import accuracy_score; from sklearn.base import clone
    fs=len(X)//(n_splits+1); scores,tr_scores,sh_scores=[],[],[]
    for fold in range(n_splits):
        te=fs*(fold+1); ts=te+embargo; te2=min(ts+fs,len(X))
        if te2>len(X) or ts>=len(X): break
        fm=clone(model); fm.fit(X[:te],y[:te])
        ta=accuracy_score(y[:te],fm.predict(X[:te]))
        pa=accuracy_score(y[ts:te2],fm.predict(X[ts:te2]))
        sh=compute_sharpe(y[ts:te2],fm.predict(X[ts:te2]))
        tr_scores.append(ta); scores.append(pa); sh_scores.append(sh)
        log.info("  Fold %d: train=%.4f test=%.4f sharpe=%.2f",fold+1,ta,pa,sh)
    return {"n_folds":len(scores),"mean_train_accuracy":float(np.mean(tr_scores)) if tr_scores else 0,
            "mean_test_accuracy":float(np.mean(scores)) if scores else 0,
            "std_test_accuracy":float(np.std(scores)) if scores else 0,
            "mean_sharpe":float(np.mean(sh_scores)) if sh_scores else 0,
            "std_sharpe":float(np.std(sh_scores)) if sh_scores else 0,
            "fold_test_scores":[float(s) for s in scores],"fold_sharpe_scores":[float(s) for s in sh_scores]}

def select_features(X,y,fn,max_features=40,quick=False):
    from sklearn.ensemble import RandomForestClassifier
    n=X.shape[1]; mask=np.ones(n,dtype=bool)
    mask[np.var(X,axis=0)<0.0003]=False
    rem=np.where(mask)[0]
    if len(rem)>1:
        corr=np.corrcoef(X[:,rem],rowvar=False); td=set()
        for i in range(len(rem)):
            for j in range(i+1,len(rem)):
                if abs(corr[i,j])>0.88: td.add(rem[j])
        for idx in td: mask[idx]=False
    rem=np.where(mask)[0]
    if len(rem)>max_features and not quick:
        rf=RandomForestClassifier(n_estimators=50,max_depth=3,random_state=42,n_jobs=-1)
        rf.fit(X[:,rem],y); top=np.argsort(rf.feature_importances_)[-max_features:]
        nm=np.zeros(n,dtype=bool); nm[rem[top]]=True; mask=nm
    names=[fn[i] for i in range(n) if mask[i]]; indices=[int(i) for i in range(n) if mask[i]]
    log.info("Selected %d: %s",len(names),names[:8]); return names,indices

def train_model(ticker,period="5y",quick=False,output_dir=None):
    from sklearn.ensemble import GradientBoostingClassifier,RandomForestClassifier
    from sklearn.linear_model import LogisticRegression; from sklearn.preprocessing import StandardScaler
    t0=time.time(); df=compute_features(ticker,period)
    fc=[c for c in df.columns if c!="target_3class"]
    clean=df[fc+["target_3class"]].dropna().iloc[:-1]
    Xf=clean[fc].values.astype(float); y=clean["target_3class"].values.astype(int)
    si=int(len(Xf)*0.8); Xtr,Xte=Xf[:si],Xf[si:]; ytr,yte=y[:si],y[si:]
    sn,si2=select_features(Xtr,ytr,fc,max_features=40,quick=quick)
    Xtr_s,Xte_s=Xtr[:,si2],Xte[:,si2]
    sc=StandardScaler(); Xtr_sc=sc.fit_transform(Xtr_s); Xte_sc=sc.transform(Xte_s)
    ne=50 if quick else 300
    cands={"rf":RandomForestClassifier(n_estimators=ne,max_depth=4,min_samples_leaf=15,max_features="sqrt",random_state=42,n_jobs=-1),
           "rf_deep":RandomForestClassifier(n_estimators=ne,max_depth=6,min_samples_leaf=10,max_features="log2",random_state=42,n_jobs=-1),
           "gbm":GradientBoostingClassifier(n_estimators=ne,max_depth=3,learning_rate=0.05,subsample=0.7,min_samples_leaf=20,random_state=42),
           "logistic":LogisticRegression(C=0.1,max_iter=2000,solver="lbfgs",random_state=42)}
    try:
        from xgboost import XGBClassifier
        cands["xgb"]=XGBClassifier(n_estimators=ne,max_depth=4,learning_rate=0.05,subsample=0.7,colsample_bytree=0.7,random_state=42,verbosity=0,use_label_encoder=False,eval_metric="mlogloss")
    except ImportError: pass
    try:
        from lightgbm import LGBMClassifier
        cands["lgbm"]=LGBMClassifier(n_estimators=ne,max_depth=4,learning_rate=0.05,subsample=0.7,colsample_bytree=0.7,random_state=42,verbose=-1)
    except ImportError: pass
    bm,bn,bs,bcv=None,None,-999,None
    for name,model in cands.items():
        cv=walk_forward_cv(model,Xtr_sc,ytr,n_splits=3 if quick else 5,embargo=5)
        log.info("  %s: acc=%.4f sharpe=%.2f",name,cv["mean_test_accuracy"],cv["mean_sharpe"])
        if cv["mean_sharpe"]>bs: bs=cv["mean_sharpe"]; bm=model; bn=name; bcv=cv
    log.info("Best %s: %s sharpe=%.2f",ticker,bn,bs); bm.fit(Xtr_sc,ytr)
    from sklearn.metrics import accuracy_score
    ta=accuracy_score(ytr,bm.predict(Xtr_sc)); pa=accuracy_score(yte,bm.predict(Xte_sc))
    psh=compute_sharpe(yte,bm.predict(Xte_sc))
    result={"ticker":ticker,"model_type":bn,"n_samples":len(Xtr)+len(Xte),"n_train":len(Xtr),"n_test":len(Xte),
            "n_features":len(sn),"feature_names":sn,"n_raw_features":len(fc),
            "train_accuracy":ta,"test_accuracy":pa,"test_sharpe":psh,"overfit_gap":ta-pa,
            "walk_forward_mean":bcv["mean_test_accuracy"],"walk_forward_std":bcv["std_test_accuracy"],
            "walk_forward_sharpe_mean":bcv["mean_sharpe"],"walk_forward_sharpe_std":bcv["std_sharpe"],
            "n_folds":bcv["n_folds"],"fold_scores":bcv["fold_test_scores"],"fold_sharpe_scores":bcv["fold_sharpe_scores"],
            "feature_version":"v4.0","target":"target_3class_0.3pct","target_thresholds":{"up":UP_THRESHOLD,"down":DOWN_THRESHOLD}}
    for cls,label in [(0,"down"),(1,"hold"),(2,"up")]:
        m=yte==cls
        if m.sum()>0: result[f"test_acc_{label}"]=accuracy_score(yte[m],bm.predict(Xte_sc)[m])
    if output_dir:
        output_dir=Path(output_dir); output_dir.mkdir(parents=True,exist_ok=True)
        ts=datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        mp=output_dir/f"{ticker}_{bn}_v4_{ts}.joblib"
        manp=output_dir/f"{ticker}_{bn}_v4_{ts}_manifest.json"
        import joblib as jb
        jb.dump({"model":bm,"model_name":bn,"scaler":sc,"feature_names":sn,
                 "metrics":{"train_accuracy":ta,"test_accuracy":pa,"test_sharpe":psh,
                            "avg_test_accuracy":bcv["mean_test_accuracy"],"avg_test_sharpe":bcv["mean_sharpe"],"overall_sharpe":psh}},mp)
        man={k:v for k,v in result.items() if k not in("fold_scores","fold_sharpe_scores")}
        man["model_path"]=str(mp.name); man["created_at"]=datetime.now(UTC).isoformat(); man["model_id"]=f"{ticker}_{bn}_v4"
        with open(manp,"w") as f: json.dump(man,f,indent=2,default=str)
        result["model_path"]=str(mp); result["manifest_path"]=str(manp); result["model_id"]=f"{ticker}_{bn}_v4"
        log.info("Saved: %s",mp)
    result["total_time_sec"]=time.time()-t0; return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--ticker",type=str); p.add_argument("--all",action="store_true")
    p.add_argument("--quick",action="store_true"); p.add_argument("--period",type=str,default="5y")
    p.add_argument("--output-dir",type=str,default=None)
    a=p.parse_args()
    tickers=["SPY","QQQ","DIA","IWM","TLT"] if a.all else [a.ticker.upper()]
    od=Path(a.output_dir) if a.output_dir else SCRIPT_DIR.parent/"models"
    results={}
    for ticker in tickers:
        log.info("="*60); log.info("Training %s...",ticker)
        try:
            r=train_model(ticker,period=a.period,quick=a.quick,output_dir=od)
            results[ticker]=r
            log.info("✓ %s: %s test=%.4f sharpe=%.2f %d feat in %.1fs",
                     ticker,r["model_type"],r["test_accuracy"],r["test_sharpe"],r["n_features"],r["total_time_sec"])
        except Exception as e:
            log.error("✗ %s: %s",ticker,e,exc_info=True); results[ticker]={"error":str(e)}
    log.info("="*60); log.info("SUMMARY")
    for t,r in results.items():
        if "error" in r: log.info("%s: ERROR %s",t,r["error"])
        else: log.info("%s: %s test=%.4f sharpe=%.2f %d feat",t,r["model_type"],r["test_accuracy"],r["test_sharpe"],r["n_features"])
    rp=SCRIPT_DIR.parent/"reports"/f"training_v4_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
    rp.parent.mkdir(exist_ok=True)
    with open(rp,"w") as q: json.dump(results,q,indent=2,default=str)
    log.info("Report: %s",rp)
    return 0 if all("error" not in r for r in results.values()) else 1

if __name__=="__main__": sys.exit(main())

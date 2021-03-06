# -*- coding: utf-8 -*-
import scipy as sp
from scipy import linalg
from kernels import KERNEL
from accuracy_index import *

def pre_compute_E_Beta(x,y,sig,kernel='RBF'):
    '''
    Function that pre computes the kernel eigenvalues/eigenfunctions during the cross-validation
    Input:
    x,y: the sample matrix and the label
    sig: the value of the kernel parameters
    Output:
    E_: a list of eigenvalues
    Beta_: a list of corresponding eigenvectors
    '''
    C = int(y.max())
    eps = sp.finfo(sp.float64).eps      
    E_=[]
    Beta_=[]

    for i in range(C):
        t = sp.where(y==(i+1))[0]
        ni=t.size
        Ki= KERNEL()
        Ki.compute_kernel(x[t,:],kernel=kernel,sig=sig)
        Ki.center_kernel()
        Ki.scale_kernel(ni)
        
        E,Beta = linalg.eigh(Ki.K)
        idx = E.argsort()[::-1]
        E = E[idx]
        E[E<eps]=eps
        Beta = Beta[:,idx]
        E_.append(E)
        Beta_.append(Beta)

    del E, Beta, Ki
    return E_,Beta_
    
def estim_d(E,threshold):
    ''' The function estimates the intrinsic dimension by looking at the cumulative variance
    Input:
        E: the eigenvalue
        threshold: the percentage of the cumulative variance
    Output:
        d: the intrinsic dimension
    '''
    if E.size == 1:
        d=1
    else:
        d = sp.where(sp.cumsum(E)/sp.sum(E)>threshold)[0][0]+1
    return d
    
def standardize(x,M=None,S=None,REVERSE=None):
    ''' Function that standardize the data
        Input:
            x: the data
            M: the mean vector
            V: the standard deviation vector
        Output:
            x: the standardize data
            M: the mean vector
            V: the standard deviation vector
    '''
    if not sp.issubdtype(x.dtype,float):
        do_convert = 1
    else:
        do_convert = 0
    if REVERSE is None:
        if M is None:
            M = sp.mean(x,axis=0)
            S = sp.std(x,axis=0)
            if do_convert:
                xs = (x.astype('float')-M)/S
            else:
                xs = (x-M)/S
            return xs,M,S
        else:
            if do_convert:
                xs = (x.astype('float')-M)/S
            else:
                xs = (x-M)/S
            return xs
    else:
        return S*x+M

def scale(x,M=None,m=None,REVERSE=None):
    ''' Function that standardize the data
        Input:
            x: the data
            M: the Max vector
            m: the Min vector
        Output:
            x: the standardize data
            M: the Max vector
            m: the Min vector
    '''
    if not sp.issubdtype(x.dtype,float):
        do_convert = 1
    else:
        do_convert = 0
    if REVERSE is None:
        if M is None:
            M = sp.amax(x,axis=0)
            m = sp.amin(x,axis=0)
            if do_convert:
                xs = 2*(x.astype('float')-m)/(M-m)-1
            else:
                xs = 2*(x-m)/(M-m)-1
            return xs,M,m
        else:
            if do_convert:
                xs = 2*(x.astype('float')-m)/(M-m)-1
            else:
                xs = 2*(x-m)/(M-m)-1
            return xs
    else:
        return (1+x)/2*(M-m)+m

class CV:
    '''
    This class implements the generation of several folds to be used in the cross validation
    '''
    def __init__(self):
        self.it=[]
        self.iT=[]

    def split_data(self,n,v=5):
        ''' The function split the data into v folds. Whatever the number of sample per class
        Input:
            n : the number of samples
            v : the number of folds
        Output: None        
        '''
        step = n //v  # Compute the number of samples in each fold
        sp.random.seed(1)   # Set the random generator to the same initial state
        t = sp.random.permutation(n)    # Generate random sampling of the indices
        
        indices=[]
        for i in range(v-1):            # group in v fold
            indices.append(t[i*step:(i+1)*step])
        indices.append(t[(v-1)*step:n])
                
        for i in range(v):
            self.iT.append(sp.asarray(indices[i]))
            l = range(v)
            l.remove(i)
            temp = sp.empty(0,dtype=sp.int64)
            for j in l:            
                temp = sp.concatenate((temp,sp.asarray(indices[j])))
            self.it.append(temp)

    def split_data_class(self,y,v=5):
        ''' The function split the data into v folds. The samples of each class are split approximatly in v folds
        Input:
            n : the number of samples
            v : the number of folds
        Output: None
        '''
        # Get parameters
        n = y.size
        C = y.max().astype('int')
       
        # Get the step for each class
        tc = []
        for j in range(v):
            tempit = []
            tempiT = []
            for i in range(C):
                # Get all samples for each class
                t  = sp.where(y==(i+1))[0]
                nc = t.size
                stepc = nc // v # Step size for each class
                if stepc == 0:
                    print "Not enough sample to build "+ str(v) +" folds in class " + str(i)                                    
                sp.random.seed(i)   # Set the random generator to the same initial state
                tc = t[sp.random.permutation(nc)] # Random sampling of indices of samples for class i
                        
                # Set testing and training samples
                if j < (v-1):
                    start,end = j*stepc,(j+1)*stepc
                else:
                    start,end = j*stepc,nc
                tempiT.extend(sp.asarray(tc[start:end])) #Testing
                k = range(v)
                k.remove(j)
                for l in k:
                    if l < (v-1):
                        start,end = l*stepc,(l+1)*stepc
                    else:
                        start,end = l*stepc,nc
                    tempit.extend(sp.asarray(tc[start:end])) #Training

            self.it.append(tempit)
            self.iT.append(tempiT)

class PGPDA: # Parcimonious Gaussian Process Discriminant Analysis
    def __init__(self,model='M0',kernel='RBF',sig=None,dc=None,threshold=None):
        self.model=model
        self.kernel=kernel
        self.sig=sig
        self.dc=dc
        self.threshold=threshold
        self.A=[]
        self.Beta=[]
        self.b = 0.0
        self.ib = 0.0
        self.a = []
        self.prop = []
        self.ni= []
        self.di = []
        self.ri = []
        self.precomputed = None
        
    def train(self,x,y,sig=None,dc=None,threshold=None,fast=None,E_=None,Beta_=None):
        '''
        The function trains the pgpda model using the training samples
        Inputs:
        x: the samples matrix of size n x d, for the precomputed case (self.precomputed==1), x is a KERNEL object.
        y: the vector with label of size n
        sig: the parameter of the kernel function
        dc: the number of dimension of the singanl subspace
        threshold: the value of the cummulative variance that should be reached
        fast = option used to perform a fast CV: only the parameter dc/threshold is learn
        
        Outputs:
        None - The model is included/updated in the object
        '''
        # Initialization
        n = y.shape[0]
        C = int(y.max())
        eps = sp.finfo(sp.float64).eps      
        list_model_dc = 'M1 M3 M4 M6'
        
        if (sig is None) and (self.sig is None):
            self.sig=0.5
        elif self.sig is None:
            self.sig = sig
        
        if (dc is None) and (self.dc is None):
            self.dc=2
        elif self.dc is None:
            self.dc = dc
            
        if (threshold is None) and (self.threshold is None):
            self.threshold=0.95
        elif self.threshold is None:
            self.threshold = threshold
        
        # Check of consistent dimension
        if (list_model_dc.find(self.model) > -1): 
            for i in range(C):
                ni = sp.size(sp.where(y==(i+1))[0])
                if self.dc > ni:
                    self.dc=ni-1
        
        for i in range(C):
            t = sp.where(y==(i+1))[0]
            self.ni.append(sp.size(t))
            self.prop.append(float(self.ni[i])/n)

            if fast is None:
                # Compute Mi
                Ki= KERNEL()
                if self.precomputed is None:
                    Ki.compute_kernel(x[t,:],kernel=self.kernel,sig=self.sig)                
                else:
                    Ki.K = x.K[t,:][:,t].copy()
                    Ki.rank = Ki.K.shape[0]
                    
                self.ri.append(Ki.rank)
                Ki.center_kernel()
                Ki.scale_kernel(self.ni[i])
                TraceKi = sp.trace(Ki.K)
            
                # Eigenvalue decomposition  
                E,Beta = linalg.eigh(Ki.K)
                idx = E.argsort()[::-1]
                E = E[idx]
                E[E<eps]=eps
                Beta = Beta[:,idx]
            else:
                E=E_[i]
                Beta=Beta_[i]
                self.ri.append(E.size)
                TraceKi = sp.sum(E)
            
            # Parameter estimation
            if list_model_dc.find(self.model) == -1:
                di = estim_d(E[0:self.ri[i]],self.threshold)
            else:
                di = self.dc
            self.di.append(di)
            self.a.append(E[0:di])
            self.b += self.prop[i]*(TraceKi-sp.sum(self.a[i]))
            self.Beta.append(Beta[:,0:di])
            del Beta,E
            
        # Last step for the safe estimation of 'b'
        denom = sum(map(lambda p,r,d:p*(r-d),self.prop,self.ri,self.di)) 
        
        if denom <eps:
            self.ib = eps
            self.b/=eps
        elif self.b <eps:
            self.ib = 1.0/eps
            self.b = eps
        else:
            self.ib = denom/self.b
            self.b /=denom
        
        # Finish the estimation for the different models
        if self.model == 'M0' or self.model == 'M1':
            for i in range(C):
                # Compute the value of matrix A
                temp =self.Beta[i]*((1/self.a[i]-self.ib)/self.a[i]).reshape(self.di[i])
                self.A.append(sp.dot(temp,self.Beta[i].T)/self.ni[i])

        elif self.model == 'M2' or self.model == 'M3':
            for i in range(C):
                # Update the value of a
                self.a[i][:]=sp.mean(self.a[i])
                # Compute the value of matrix A
                temp =self.Beta[i]*((1/self.a[i]-self.ib)/self.a[i]).reshape(self.di[i])
                self.A.append(sp.dot(temp,self.Beta[i].T)/self.ni[i])

        elif self.model == 'M4': 
            # Compute the value of a
            al = sp.zeros((self.dc))
            for i in range(self.dc):
                for j in range(C):
                    al[i] += self.prop[j]*self.a[j][i]
            for i in range(C):
                self.a[i]=al.copy()
                temp =self.Beta[i]*((1/self.a[i]-self.ib)/self.a[i]).reshape(self.di[i])
                self.A.append(sp.dot(temp,self.Beta[i].T)/self.ni[i])

        elif self.model == 'M5' or self.model=='M6':
            num = sum(map(lambda p,a:p*sum(a),self.prop,self.a))
            den = sum(map(lambda p,d:p*d,self.prop,self.di))
            ac = num/den
            for i in range(C):
                self.a[i][:]=ac
                temp =self.Beta[i]*((1/self.a[i]-self.ib)/self.a[i]).reshape(self.di[i])
                self.A.append(sp.dot(temp,self.Beta[i].T)/self.ni[i])
                
        self.A = sp.asarray(self.A)   

       
    def predict(self,xt,x,y,out_decision=None,out_proba=None):
        '''
        The function predicts the label for each sample with the learned model
        Input:
            xt: the test samples
            x: the samples matrix of size n x d
            y: the vector with label of size n
        Output
            yp: the label
            D: the discriminant function
            P: the posterior probabilities
        '''
         
        # Initialization
        if isinstance(xt,sp.ndarray):
            nt = xt.shape[0]
        else:
            nt = xt.K.shape[0]
            
        C = int(y.max())
        eps = sp.finfo(sp.float64).eps
        dm = max(self.di)

        D = sp.empty((nt,C))
        Ki = KERNEL()
        Kt = KERNEL()
        kd = KERNEL()
        
        for i in range(C):
            t = sp.where(y==(i+1))[0]
            cst = sp.sum(sp.log(self.a[i])) + (dm-self.di[i])*sp.log(self.b) -2*sp.log(self.prop[i]) 
            if self.precomputed is None:
                Ki.compute_kernel(x[t,:],kernel=self.kernel,sig=self.sig)
                Kt.compute_kernel(xt,z=x[t,:],kernel=self.kernel,sig=self.sig)
                kd.compute_diag_kernel(xt,kernel=self.kernel,sig=self.sig)
            else:
                Ki.K= x.K[t,:][:,t].copy()
                Kt.K= xt.K[:,t].copy()
                kd.K= xt.kd.copy()
            Kt.center_kernel(Ko=Ki, kd=kd)
            Ki.K=None

            #Compute the decision rule
            temp = sp.dot(Kt.K,self.A[i])
            D[:,i] = sp.sum(Kt.K*temp,axis=1)
            D[:,i] += kd.K*self.ib+cst           
            
        # Check if negative value
        if D.min() <0:
            D-=D.min()
        
        yp = D.argmin(1)+1
        yp.shape=(nt,1)

        # Format the output
        if out_proba is None:
            if out_decision is None:
                return yp
            else:
                return yp,D
        else:        
            # Compute posterior !! Should be changed to a safe version
            P = sp.exp(-0.5*D)
            P /= sp.sum(P,axis=1).reshape(nt,1)
            P[P<eps]=0                    
        return yp,D,P
    
    def cross_validation(self,x,y,v=5,sig_r=2.0**sp.arange(-8,0),threshold_r=sp.linspace(0.85,0.9999,10),dc_r=sp.arange(5,50)):
        '''
        To be done and can be changed by using pre-computed kernels
        '''
        # Get parameters
        n=x.shape[0]
        ns = sig_r.size
        nt = threshold_r.size
        nd = dc_r.size
        if self.model == 'M0' or self.model=='M2' or self.model =='M5':
            err = sp.zeros((ns,nt))
        else:
            err = sp.zeros((ns,nd))
            
        # Initialization of the indices for the cross validation
        cv = CV()           
        cv.split_data_class(y,v=v)
        
        # Start the cross-validation
        if self.model == 'M0' or self.model=='M2' or self.model =='M5':
            for i in range(ns):
                for k in range(v):
                    # Precompute the E and Beta
                    E_,Beta_=pre_compute_E_Beta(x[cv.it[k],:],y[cv.it[k]],sig_r[i])
                    # test several threshold
                    for j in range(nt):
                        model_temp = PGPDA(model=self.model,kernel=self.kernel)
                        model_temp.train(x[cv.it[k],:],y[cv.it[k]],sig=sig_r[i],threshold=threshold_r[j],fast=1,E_=E_,Beta_=Beta_)
                        yp = model_temp.predict(x[cv.iT[k],:],x[cv.it[k],:],y[cv.it[k]])
                        yp.shape = y[cv.iT[k]].shape                        
                        t = sp.where(yp!=y[cv.iT[k]])[0]
                        err[i,j]+= float(t.size)/yp.size
                        del model_temp
            err/=v
            t = sp.where(err==err.min())
            self.sig = sig_r[t[0][0]]
            self.threshold = threshold_r[t[1][0]]
            return sig_r[t[0][0]],threshold_r[t[1][0]],err
                        
        else:
            for i in range(ns):
                for k in range(v):
                    # Precompute the E and Beta
                    E_,Beta_=pre_compute_E_Beta(x[cv.it[k],:],y[cv.it[k]],sig_r[i])
                    # test several threshold
                    for j in range(nd):
                        model_temp = PGPDA(model=self.model,kernel=self.kernel)
                        model_temp.train(x[cv.it[k],:],y[cv.it[k]],sig=sig_r[i],dc=dc_r[j],fast=1,E_=E_,Beta_=Beta_)
                        yp = model_temp.predict(x[cv.iT[k],:],x[cv.it[k],:],y[cv.it[k]])
                        yp.shape = y[cv.iT[k]].shape
                        t = sp.where(yp!=y[cv.iT[k]])[0]
                        err[i,j]+= float(t.size)/yp.size
                        del model_temp
            err/=v
            t = sp.where(err==err.min())
            self.sig = sig_r[t[0][0]]
            self.dc = dc_r[t[1][0]]
            return sig_r[t[0][0]],dc_r[t[1][0]],err

class NPGPDA: # Parcimonious Gaussian Process Discriminant Analysis with class specific noise
    def __init__(self,model='NM0',kernel='RBF',sig=None,dc=None,threshold=None):
        self.model=model
        self.kernel=kernel
        self.sig=sig
        self.dc=dc
        self.threshold=threshold
        self.A=[]
        self.Beta=[]
        self.b = []
        self.ib = []
        self.a = []
        self.prop = []
        self.ni= []
        self.di = []
        self.ri = []
        self.precomputed = None

    def train(self,x,y,sig=None,dc=None,threshold=None,fast=None,E_=None,Beta_=None):
        '''
        The function trains the pgpda model using the training samples
        Inputs:
        x: the samples matrix of size n x d, for the precomputed case (self.precomputed==1), x is a KERNEL object.
        y: the vector with label of size n
        sig: the parameter of the kernel function
        dc: the number of dimension of the singanl subspace
        threshold: the value of the cummulative variance that should be reached
        fast = option used to perform a fast CV: only the parameter dc/threshold is learn
        
        Outputs:
        None - The model is included/updated in the object
        '''

        # Initialization
        n = y.shape[0]
        C = int(y.max())
        eps = sp.finfo(sp.float64).eps      
        list_model_dc = 'NM1 NM3 NM4'
        
        if (sig is None) and (self.sig is None):
            self.sig=0.5
        elif self.sig is None:
            self.sig = sig
        
        if (dc is None) and (self.dc is None):
            self.dc=2
        elif self.dc is None:
            self.dc = dc
            
        if (threshold is None) and (self.threshold is None):
            self.threshold=0.95
        elif self.threshold is None:
            self.threshold = threshold
        
        # Check of consistent dimension
        if (list_model_dc.find(self.model) > -1): 
            for i in range(C):
                ni = sp.size(sp.where(y==(i+1))[0])
                if self.dc >= ni-1:
                    self.dc=ni-2

        # Estimate the parameters of each class
        for i in range(C):
            t = sp.where(y==(i+1))[0]
            self.ni.append(sp.size(t))
            self.prop.append(float(self.ni[i])/n)

            if fast is None:
                # Compute Mi
                Ki= KERNEL()
                if self.precomputed is None:
                    Ki.compute_kernel(x[t,:],kernel=self.kernel,sig=self.sig)                
                else:
                    Ki.K = x.K[t,:][:,t].copy()
                    Ki.rank = Ki.K.shape[0]
                    
                self.ri.append(Ki.rank-1)
                Ki.center_kernel()
                Ki.scale_kernel(self.ni[i])
                TraceKi = sp.trace(Ki.K)
            
                # Eigenvalue decomposition  
                E,Beta = linalg.eigh(Ki.K)
                idx = E.argsort()[::-1]
                E = E[idx]
                E[E<eps]=eps
                Beta = Beta[:,idx]
            else:
                E=E_[i]
                Beta=Beta_[i]
                self.ri.append(E.size-1)
                TraceKi = sp.sum(E)
            
            # Parameter estimation
            if list_model_dc.find(self.model) == -1:
                di = estim_d(E[0:self.ri[i]-1],self.threshold)
            else:
                di = self.dc
            self.di.append(di)
            self.a.append(E[0:di])
            self.b.append((TraceKi-sp.sum(self.a[i]))/(self.ri[i]-di))

            if self.b[i] < eps:# Sanity check for numerical precision
                self.b[i] = eps
                self.ib.append(1.0/eps)
            else:
                self.ib.append(1/self.b[i])                
            self.Beta.append(Beta[:,0:di])
            del Beta,E

            
        # Finish the estimation for the different models
        if self.model == 'NM0' or self.model == 'NM1':
            for i in range(C):
                # Compute the value of matrix A
                temp =self.Beta[i]*((1/self.a[i]-self.ib[i])/self.a[i]).reshape(self.di[i])
                self.A.append(sp.dot(temp,self.Beta[i].T)/self.ni[i])

        elif self.model == 'NM2' or self.model == 'NM3':
            for i in range(C):
                # Update the value of a
                self.a[i][:]=sp.mean(self.a[i])
                # Compute the value of matrix A
                temp =self.Beta[i]*((1/self.a[i]-self.ib[i])/self.a[i]).reshape(self.di[i])
                self.A.append(sp.dot(temp,self.Beta[i].T)/self.ni[i])

        elif self.model == 'NM4': 
            # Compute the value of a
            al = sp.zeros((self.dc))
            for i in range(self.dc):
                for j in range(C):
                    al[i] += self.prop[j]*self.a[j][i]
            for i in range(C):
                self.a[i]=al.copy()
                temp =self.Beta[i]*((1/self.a[i]-self.ib[i])/self.a[i]).reshape(self.di[i])
                self.A.append(sp.dot(temp,self.Beta[i].T)/self.ni[i])

        self.A = sp.asarray(self.A)


    def predict(self,xt,x,y,out_decision=None,out_proba=None):
        '''
        The function predicts the label for each sample with the learned model
        Input:
            xt: the test samples
            x: the samples matrix of size n x d
            y: the vector with label of size n
        Output
            yp: the label
            D: the discriminant function
            P: the posterior probabilities
        '''
         
        # Initialization
        if isinstance(xt,sp.ndarray):
            nt = xt.shape[0]
        else:
            nt = xt.K.shape[0]
            
        C = int(y.max())
        eps = sp.finfo(sp.float64).eps
        dm = max(self.di)

        D = sp.empty((nt,C))
        Ki = KERNEL()
        Kt = KERNEL()
        kd = KERNEL()
        
        for i in range(C):
            t = sp.where(y==(i+1))[0]
            cst = sp.sum(sp.log(self.a[i])) + (self.ri[i]-self.di[i])*sp.log(self.b[i]) -2*sp.log(self.prop[i]) 
            if self.precomputed is None:
                Ki.compute_kernel(x[t,:],kernel=self.kernel,sig=self.sig)
                Kt.compute_kernel(xt,z=x[t,:],kernel=self.kernel,sig=self.sig)
                kd.compute_diag_kernel(xt,kernel=self.kernel,sig=self.sig)
            else:
                Ki.K= x.K[t,:][:,t].copy()
                Kt.K= xt.K[:,t].copy()
                kd.K= xt.kd.copy()
            Kt.center_kernel(Ko=Ki, kd=kd)
            Ki.K=None

            #Compute the decision rule
            temp = sp.dot(Kt.K,self.A[i])
            D[:,i] = sp.sum(Kt.K*temp,axis=1)
            D[:,i] += kd.K*self.ib[i]+cst           
            
        # Check if negative value
        if D.min() <0:
            D-=D.min()
        
        yp = D.argmin(1)+1
        yp.shape=(nt,1)

        # Format the output
        if out_proba is None:
            if out_decision is None:
                return yp
            else:
                return yp,D
        else:        
            # Compute posterior !! Should be changed to a safe version
            P = sp.exp(-0.5*D)
            P /= sp.sum(P,axis=1).reshape(nt,1)
            P[P<eps]=0                    
        return yp,D,P

    def cross_validation(self,x,y,v=5,sig_r=2.0**sp.arange(-8,0),threshold_r=sp.linspace(0.85,0.9999,10),dc_r=sp.arange(5,50)):
        '''
        To be done and can be changed by using pre-computed kernels
        '''
        # Get parameters
        n=x.shape[0]
        ns = sig_r.size
        nt = threshold_r.size
        nd = dc_r.size
        if self.model == 'NM0' or self.model=='NM2' or self.model =='NM5':
            err = sp.zeros((ns,nt))
        else:
            err = sp.zeros((ns,nd))
            
        # Initialization of the indices for the cross validation
        cv = CV()           
        cv.split_data_class(y,v=v)
        
        # Start the cross-validation
        if self.model == 'NM0' or self.model=='NM2' or self.model =='NM5':
            for i in range(ns):
                for k in range(v):
                    # Precompute the E and Beta
                    E_,Beta_=pre_compute_E_Beta(x[cv.it[k],:],y[cv.it[k]],sig_r[i])
                    # test several threshold
                    for j in range(nt):
                        model_temp = NPGPDA(model=self.model,kernel=self.kernel)
                        model_temp.train(x[cv.it[k],:],y[cv.it[k]],sig=sig_r[i],threshold=threshold_r[j],fast=1,E_=E_,Beta_=Beta_)
                        yp = model_temp.predict(x[cv.iT[k],:],x[cv.it[k],:],y[cv.it[k]])
                        yp.shape = y[cv.iT[k]].shape                        
                        t = sp.where(yp!=y[cv.iT[k]])[0]
                        err[i,j]+= float(t.size)/yp.size
                        del model_temp
            err/=v
            t = sp.where(err==err.min())
            self.sig = sig_r[t[0][0]]
            self.threshold = threshold_r[t[1][0]]
            return sig_r[t[0][0]],threshold_r[t[1][0]],err
                        
        else:
            for i in range(ns):
                for k in range(v):
                    # Precompute the E and Beta
                    E_,Beta_=pre_compute_E_Beta(x[cv.it[k],:],y[cv.it[k]],sig_r[i])
                    # test several threshold
                    for j in range(nd):
                        model_temp = NPGPDA(model=self.model,kernel=self.kernel)
                        model_temp.train(x[cv.it[k],:],y[cv.it[k]],sig=sig_r[i],dc=dc_r[j],fast=1,E_=E_,Beta_=Beta_)
                        yp = model_temp.predict(x[cv.iT[k],:],x[cv.it[k],:],y[cv.it[k]])
                        yp.shape = y[cv.iT[k]].shape
                        t = sp.where(yp!=y[cv.iT[k]])[0]
                        err[i,j]+= float(t.size)/yp.size
                        del model_temp
            err/=v
            t = sp.where(err==err.min())
            self.sig = sig_r[t[0][0]]
            self.dc = dc_r[t[1][0]]
            return sig_r[t[0][0]],dc_r[t[1][0]],err

class KDA: # Kernel QDA from "Toward an Optimal Supervised Classifier for the Analysis of Hyperspectral Data"
    def __init__(self,mu=None,sig=None):
        self.a = []
        self.A = []
        self.S = []
        self.ni = []
        self.prop=[]
        self.sig=sig
        self.mu=mu
    
    def train(self,x,y,mu=None,sig=None):
        # Initialization
        n = y.shape[0]
        C = int(y.max())
        eps = sp.finfo(sp.float64).eps 
        
        if (mu is None) and (self.mu is None):
            mu=10**(-7)
        elif self.mu is None:
            self.mu =mu
            
        if (sig is None) and (self.sig is None):
            self.sig=0.5
        elif self.sig is None:
            self.sig=sig
        
        # Compute K and 
        K = KERNEL()
        K.compute_kernel(x,sig=self.sig)
        G = KERNEL()
        G.K = self.mu*sp.eye(n)
                    
        for i in range(C):
            t = sp.where(y==(i+1))[0]
            self.ni.append(sp.size(t))
            self.prop.append(float(self.ni[i])/n)
        
            # Compute K_k
            Ki = KERNEL()
            Ki.compute_kernel(x, z=x[t,:],sig=self.sig)
            T = (sp.eye(self.ni[i])-sp.ones((self.ni[i],self.ni[i])))
            Ki.K = sp.dot(Ki.K,T)
            del T
            G.K += sp.dot(Ki.K,Ki.K.T)/self.ni[i]
        G.scale_kernel(C)
        
        # Solve the generalized eigenvalue problem
        a,A = linalg.eigh(G.K,b=K.K)
        idx = a.argsort()[::-1]
        a=a[idx]
        A=A[:,idx]
        
        # Remove negative eigenvalue
        t = sp.where(a>eps)[0]
        a=a[t]
        A=A[:,t]
        
        # Normalize the eigenvalue
        for i in range(a.size):
            A[:,i]/=sp.sqrt(sp.dot(sp.dot(A[:,i].T,K.K),A[:,i]))
        
        # Update model   
        self.a=a.copy()
        self.A=A.copy()
        self.S= sp.dot(sp.dot(self.A,sp.diag(self.a**(-1))),self.A.T)
        
        # Free memory
        del G,K,a,A
    
    def predict(self,xt,x,y,out_decision=None,out_proba=None):
        nt = xt.shape[0]
        C = int(y.max())
        D = sp.empty((nt,C))
        D += self.prop
        eps = sp.finfo(sp.float64).eps
        
        # Pre compute the Gramm kernel matrix
        Kt = KERNEL()
        Kt.compute_kernel(xt,z=x,sig=self.sig)
        Ki = KERNEL()
                
        for i in range(C):
            t = sp.where(y==(i+1))[0]
            Ki.compute_kernel(x,z=x[t,:],sig=self.sig)
            T = Kt.K - sp.dot(Ki.K,sp.ones((self.ni[i]))/self.ni[i])
            temp = sp.dot(T,self.S)
            D[:,i] = sp.sum(T*temp,axis=1)
        
        # Check if negative value
        if D.min() <0:
            D-=D.min()
        
        yp = D.argmin(1)+1
        yp.shape=(nt,1)

        # Format the output
        if out_proba is None:
            if out_decision is None:
                return yp
            else:
                return yp,D
        else:        
            # Compute posterior !! Should be changed to a safe version
            P = sp.exp(-0.5*D)
            P /= sp.sum(P,axis=1).reshape(nt,1)
            P[P<eps]=0                    
        return yp,D,P
    
    def cross_validation(self,x,y,v=5,sig_r=2.0**sp.arange(-8,0),mu_r=10.0**sp.arange(-15,0)):
        # Get parameters
        n=x.shape[0]
        ns = sig_r.size
        nm = mu_r.size
        err = sp.zeros((ns,nm))
        
        # Initialization of the indices for the cross validation
        cv = CV()           
        cv.split_data_class(y,v=v)
        
        for i in range(ns):
            for j in range(nm):
                for k in range(v):
                    model_temp=KDA()
                    model_temp.train(x[cv.it[k],:],y[cv.it[k]],sig=sig_r[i],mu=mu_r[j])
                    yp = model_temp.predict(x[cv.iT[k],:],x[cv.it[k],:],y[cv.it[k]])
                    yp.shape = y[cv.iT[k]].shape
                    t = sp.where(yp!=y[cv.iT[k]])[0]
                    err[i,j]+= float(t.size)/yp.size
                    del model_temp
        err/=v
        t = sp.where(err==err.min())
        self.sig = sig_r[t[0][0]]
        self.mu = mu_r[t[1][0]]
        return sig_r[t[0][0]],mu_r[t[1][0]],err
                    
                


"""
#########################################
Snmnmf (``methods.factorization.snmnmf``)
#########################################

**Sparse Network-Regularized Multiple Nonnegative Matrix Factorization (SNMNMF)** [Zhang2011]_.

It is semi-supervised learning method with constraints (e. g. in comodule identification, any variables linked in 
A or B, are more likely placed in the same comodule) to improve relevance and narrow down the search space.

The advantage of this method is the integration of multiple matrices for multiple types of variables (standard NMF
methods can be applied to a target matrix containing just one type of variable) together with prior knowledge 
(e. g. network representing relationship among variables). 

The objective function in [Zhang2011]_ has three components:
    #. first component models miRNA and gene expression profiles;
    #. second component models gene-gene network interactions;
    #. third component models predicted miRNA-gene interactions.
 
The inputs for the SNMNMF are:
    #. two sets of expression profiles (represented by the matrices V and V1 of shape s x m, s x n, respectively) for 
       miRNA and genes measured on the same set of samples;
    #. (PRIOR KNOWLEDGE) a gene-gene interaction network (represented by the matrix A of shape n x n), including protein-protein interactions
       and DNA-protein interactions;
    #. (PRIOR KNOWLEDGE) a list of predicted miRNA-gene regulatory interactions (represented by the matrix B of shape m x n) based on
       sequence data. 
Gene and miRNA expression matrices are simultaneously factored into a common basis matrix (W) and two
coefficients matrices (H and H1). Additional knowledge is incorporated into this framework with network 
regularized constraints. Because of the imposed sparsity constraints easily interpretable solution is obtained. 

.. literalinclude:: /code/methods_snippets.py
    :lines: 2-15
    
"""

from mf.models import *
from mf.utils import *
from mf.utils.linalg import *

class Snmnmf(nmf_mm.Nmf_mm):
    """
    For detailed explanation of the general model parameters see :mod:`mf_run`.
    
    The following are algorithm specific model options which can be passed with values as keyword arguments.
    
    :param A: Adjacency matrix of gene-gene interaction network (dimension: V1.shape[1] x V1.shape[1]). It should be 
              nonnegative. Default is scipy.sparse CSR matrix of density 0.7.
    :type A: :class:`scipy.sparse` of format csr, csc, coo, bsr, dok, lil, dia or :class:`numpy.matrix` 
    :param B: Adjacency matrix of a bipartite miRNA-gene network, predicted miRNA-target interactions 
              (dimension: V.shape[1] x V1.shape[1]). It should be nonnegative. Default is scipy.sparse 
              CSR matrix of density 0.7.
    :type B: :class:`scipy.sparse` of format csr, csc, coo, bsr, dok, lil, dia or :class:`numpy.matrix` 
    :param gamma: Limit the growth of the basis matrix (W). Default is 0.01.
    :type gamma: `float`
    :param gamma_1: Limit the growth of the mixture matrices (H and H1). Default is 0.01.
    :type gamma_1: `float`
    :param lamb: Weight for the must-link constraints defined in :param:`A`. Default is 0.01.
    :type lamb: `float`
    :param lamb_1: Weight for the must-link constraints define in :param:`B`. Default is 0.01.
    :type lamb_1: `float`
    """

    def __init__(self, **params):
        self.name = "snmnmf"
        self.aseeds = ["random", "fixed", "nndsvd", "random_c", "random_vcol"]
        nmf_mm.Nmf_mm.__init__(self, params)
        self.set_params()
        
    def factorize(self):
        """
        Compute matrix factorization.
         
        Return fitted factorization model.
        """
        if self.V.shape[0] != self.V1.shape[0]:
            raise utils.MFError("Input matrices should have the same number of rows.")
                
        for run in xrange(self.n_run):
            self.options.update({'idx' : 0})
            self.W, self.H = self.seed.initialize(self.V, self.rank, self.options)
            self.options.update({'idx' : 1})
            _, self.H1 = self.seed.initialize(self.V1, self.rank, self.options)
            self.options.pop('idx')
            p_obj = c_obj = self.objective()
            best_obj = c_obj if run == 0 else best_obj
            iter = 0
            while self.is_satisfied(p_obj, c_obj, iter):
                p_obj = c_obj if not self.test_conv or iter % self.test_conv == 0 else p_obj
                self.update(iter)
                c_obj = self.objective() if not self.test_conv or iter % self.test_conv == 0 else c_obj
                iter += 1
                if self.track_error:
                    self.tracker.track_error(c_obj, run)
            if self.callback:
                self.final_obj = c_obj
                mffit = mf_fit.Mf_fit(self) 
                self.callback(mffit)
            if self.track_factor:
                self.tracker.track_factor(W = self.W.copy(), H = self.H.copy(), H1 = self.H1.copy(), 
                                          final_obj = c_obj, n_iter = iter)
            # if multiple runs are performed, fitted factorization model with the lowest objective function value is retained 
            if c_obj <= best_obj or run == 0:
                best_obj = c_obj
                self.n_iter = iter 
                self.final_obj = c_obj
                mffit = mf_fit.Mf_fit(self)
                
        return mffit
        
    def is_satisfied(self, p_obj, c_obj, iter):
        """
        Compute the satisfiability of the stopping criteria based on stopping parameters and objective function value.
        
        Return logical value denoting factorization continuation. 
        
        :param p_obj: Objective function value from previous iteration. 
        :type p_obj: `float`
        :param c_obj: Current objective function value.
        :type c_obj: `float`
        :param iter: Current iteration number. 
        :type iter: `int`
        """
        if self.test_conv and iter % self.test_conv != 0:
            return True
        if self.err_avg < 1e-5:
            return False
        if self.max_iter and self.max_iter <= iter:
            return False
        if self.min_residuals and iter > 0 and p_obj - c_obj < self.min_residuals:
            return False
        if iter > 0 and c_obj > p_obj:
            return False
        return True
    
    def set_params(self):
        """Set algorithm specific model options."""
        self.A = self.options.get('A', abs(sp.rand(self.V1.shape[1], self.V1.shape[1], density = 0.7, format = 'csr')))
        if sp.isspmatrix(self.A):
            self.A = self.A.tocsr()
        else:
            self.A = np.mat(self.A)
        self.B = self.options.get('B', abs(sp.rand(self.V.shape[1], self.V1.shape[1], density = 0.7, format = 'csr')))
        if sp.isspmatrix(self.B):
            self.B = self.B.tocsr()
        else:
            self.B = np.mat(self.B)
        self.gamma = self.options.get('gamma', 0.01)
        self.gamma_1 = self.options.get('gamma_1', 0.01)
        self.lamb = self.options.get('lamb', 0.01)
        self.lamb_1 = self.options.get('lamb_1', 0.01)
        self.track_factor = self.options.get('track_factor', False)
        self.track_error = self.options.get('track_error', False)
        self.tracker = mf_track.Mf_track() if self.track_factor and self.n_run > 1 or self.track_error else None
        
    def update(self, iter):
        """Update basis and mixture matrix."""
        # update basis matrix
        temp_w1 = dot(self.V, self.H.T) + dot(self.V1, self.H1.T)
        temp_w2 = dot(self.W, dot(self.H, self.H.T) + dot(self.H1, self.H1.T)) + self.gamma / 2. * self.W
        self.W = multiply(self.W, elop(temp_w1, temp_w2, div))
        # update mixture matrices
        # update H1
        temp = sop(dot(self.W.T, self.W), s = self.gamma_1, op = add)
        temp_h1 = dot(self.W.T, self.V) + self.lamb_1 / 2. * dot(self.H1, self.B.T)
        HH1 = multiply(self.H, elop(temp_h1, dot(temp, self.H), div))
        temp_h3 = dot(self.W.T, self.V1) + self.lamb * dot(self.H1, self.A) + self.lamb_1 / 2. * dot(self.H, self.B)
        temp_h4 = dot(temp, self.H1)
        self.H1 = multiply(self.H1, elop(temp_h3, temp_h4, div))
        #update H
        self.H = HH1
                    
    def objective(self):
        """Compute three component objective function as defined in [Zhang2011]_.""" 
        err_avg1 = abs(self.V - dot(self.W, self.H)).mean() / self.V.mean()
        err_avg2 = abs(self.V1 - dot(self.W, self.H1)).mean() / self.V1.mean()
        self.err_avg = err_avg1 + err_avg2
        eucl1 = (sop(self.V - dot(self.W, self.H), 2, pow)).sum()
        eucl2 = (sop(self.V1 - dot(self.W, self.H1), 2, pow)).sum()
        tr1 = trace(dot(dot(self.H1, self.A), self.H1.T))
        tr2 = trace(dot(dot(self.H, self.B), self.H1.T))
        s1 = sop(self.W, 2, pow).sum()
        s2 = sop(self.H, 2, pow).sum() + sop(self.H1, 2, pow).sum()
        return eucl1 + eucl2 - self.lamb * tr1 - self.lamb_1 * tr2 + self.gamma * s1 + self.gamma_1 * s2
    
    def __str__(self):
        return self.name
    
    def __repr__(self):
        return self.name 
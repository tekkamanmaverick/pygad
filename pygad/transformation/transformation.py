'''
Classes for snapshot transformations.

Examples:
    >>> from ..environment import module_dir
    >>> from ..snapshot import Snap
    >>> rot = Rotation([[0,1,0],[1,0,0],[0,0,1]])
    Traceback (most recent call last):
    ...
    ValueError: Rotation matrix needs to fullfil det(R) == +1 (proper Rotation)!
    >>> rot = Rotation([[0,1,0],[0,0,1],[1,0,0]])
    >>> s = Snap(module_dir+'../snaps/snap_M1196_4x_470', physical=False)
    >>> s.pos[:3]
    load block pos... done.
    SimArr([[ 34613.515625  ,  35521.81640625,  33178.60546875],
            [ 34613.296875  ,  35521.765625  ,  33178.31640625],
            [ 34613.26171875,  35521.8828125 ,  33178.48046875]],
           dtype=float32, units="ckpc h_0**-1", snap="snap_M1196_4x_470")
    >>> rot.apply(s)
    apply Rotation to "pos" of "snap_M1196_4x_470"... done.
    >>> s.pos[:3]
    SimArr([[ 35521.81640625,  33178.60546875,  34613.515625  ],
            [ 35521.765625  ,  33178.31640625,  34613.296875  ],
            [ 35521.8828125 ,  33178.48046875,  34613.26171875]],
           dtype=float32, units="ckpc h_0**-1", snap="snap_M1196_4x_470")
    >>> s.vel[:3]
    load block vel... done.
    apply stored Rotation to block vel... done.
    SimArr([[-119.9617691 , -215.21350098, -218.84106445],
            [-100.0279007 , -203.89819336, -218.8409729 ],
            [-107.25678253, -204.94604492, -213.70817566]],
           dtype=float32, units="s**-1 km", snap="snap_M1196_4x_470")
    >>> Translation(UnitArr([10,-20,30],'Mpc')).apply(s)
    apply Translation to "pos" of "snap_M1196_4x_470"... done.
    >>> s.pos[:3]
    SimArr([[ 42721.81640625,  18778.60546875,  56213.515625  ],
            [ 42721.765625  ,  18778.31640625,  56213.296875  ],
            [ 42721.8828125 ,  18778.48046875,  56213.26171875]],
           dtype=float32, units="ckpc h_0**-1", snap="snap_M1196_4x_470")
    >>> Translation(UnitArr([100,200,300])).apply(s)
    apply Translation to "pos" of "snap_M1196_4x_470"... done.
    >>> rot.apply(s)
    apply Rotation to "vel" of "snap_M1196_4x_470"... done.
    apply Rotation to "pos" of "snap_M1196_4x_470"... done.
    >>> ca, sa = np.cos(12), np.sin(12)
    >>> Rotation([[ca,sa,0],[-sa,ca,0],[0,0,1]]).apply(s)
    apply Rotation to "vel" of "snap_M1196_4x_470"... done.
    apply Rotation to "pos" of "snap_M1196_4x_470"... done.
    >>> for T in s._trans_at_load:  # for efficiency, translations of same type
    ...     print T                 # are combined...
    Rotation([[ 0.000, 1.000, 0.000],[ 0.000, 0.000, 1.000],[ 1.000, 0.000, 0.000]])
    Translation([10.14,-19.72,30.42] [Mpc])
    Rotation([[ 0.000, 0.844,-0.537],[ 0.000, 0.537, 0.844],[ 1.000, 0.000, 0.000]])
    >>> old = s.pos[:3]
    >>> del s.pos
    >>> assert np.max(np.abs((s.pos[:3] - old) / old)) < 1e-6
    load block pos... done.
    apply stored Rotation to block pos... done.
    apply stored Translation to block pos... done.
    apply stored Rotation to block pos... done.
    >>> del s; s = Snap(module_dir+'../snaps/snap_M1196_4x_470', physical=False)
    >>> print s.pos[0]; print s.pos[-1]
    load block pos... done.
    [ 34613.515625    35521.81640625  33178.60546875] [ckpc h_0**-1]
    [ 34607.65234375  35537.62109375  33167.83203125] [ckpc h_0**-1]
    >>> rot.apply(s.gas,remember=False)
    apply Rotation to "pos" of "snap_M1196_4x_470":gas... done.
    >>> print s.pos[0]; print s.pos[-1]
    [ 35521.81640625  33178.60546875  34613.515625  ] [ckpc h_0**-1]
    [ 34607.65234375  35537.62109375  33167.83203125] [ckpc h_0**-1]
    >>> del s.pos

    >>> np.linalg.norm(s.pos[0])
    load block pos... done.
    59671.727
    >>> rot_to_z([1,0,0]).apply(s.gas, total=True)
    apply Rotation to "pos" of "snap_M1196_4x_470"... done.
    >>> np.linalg.norm(s.pos[0])
    59671.727
    >>> s.vel[-3:]
    load block vel... done.
    apply stored Rotation to block vel... done.
    SimArr([[  14.27710342,  -56.8183403 ,   54.35939789],
            [  37.94758224,   84.52431488,  130.14624023],
            [  37.37803268,   64.14741516,   -4.18749571]],
           dtype=float32, units="s**-1 km", snap="snap_M1196_4x_470")
'''
__all__ = ['Transformation', 'Translation', 'Rotation', 'rot_from_axis_angle',
           'rot_to_z']

import sys
import numpy as np
from ..units import *
from .. import environment

class Transformation(object):
    '''
    The base-class for transformations.

    Args:
        change (dict):  A dictionary from the block names to the functions to call
                        when the transformation is applied to them in self.apply.
                        They have to have the call signature f(name,snap).
    '''

    def __init__(self, change, pre=None, post=None):
        self._change = change.copy()
        self._pre  = [] if pre  is None else pre.copy()
        self._post = [] if post is None else prost.copy()

    @property
    def changes(self):
        '''The names of the blocks that are changed, if applied to a snapshot.'''
        return self._change.keys()

    def _apply_to_block(self, block, snap=None):
        raise NotImplementedError('This is just an interface / a virtual base '
                                  'class!')

    def apply_to_block(self, block, snap=None):
        '''
        Apply the transformation to a single block.

        Args:
            block (np.ndarray, str):    The block to apply the transformation to.
                                        If snap==None, this has to be an array,
                                        which then is not changed in-place; else
                                        if snap is a snapshot, it has to be a
                                        string an the block is transformed
                                        in-place (if possible) in the snapshot.
            snap (Snap):                The snapshot the block belongs to (c.f.
                                        above).

        Returns:
            transformed (array-like):   The transformed block (also if changed
                                        in-place).
        '''
        if isinstance(block,str) and block in self._change:
            return self._change[block](block,snap)
        else:
            return self._apply_to_block(block,snap)

    def apply(self, snap, total=False, remember=True, fams=True, exclude=None):
        '''
        Apply the transformation to all available and already loaded/derived
        blocks in the snapshot.

        Args:
            snap (Snap):    The snapshot to which the transformation shall be
                            applied. It can be a sub-snapshot, then the trans-
                            formation is only applied to that.
            total (bool):   Whether to apply the transformation to the entire
                            snapshot or just the passed sub-snapshot. A total=True
                            overwrites the argument snap to snap.root.
            remember (bool):
                            If set to True and the transformation is applied to
                            the root snapshot (which is always true if 'total' is
                            set), the snapshot remembers the transformation and
                            also applies it to newly loaded blocks.
            fams (bool):    Whether to include the blocks that are only available
                            for some of the particle types.
            exclude (set, list, tuple): 
                            Some object that supports the operator 'in'. Block
                            names that are in exclude are skipped.
        '''
        if total and snap is not snap.root:
            snap = snap.root
        if exclude is None:
            exclude = set()

        done = set()
        # do blocks specified in 'self._pre' first and those in 'self._post' in
        # the end
        todo = self._pre \
             + list(set(self._change)-set(self._pre)-set(self._post)) \
             + self._post
        for name in todo:
            # only apply to available and not excluded blocks
            if name not in snap.available_blocks() or name in exclude:
                continue
            # ... and do not load blocks here
            if name not in snap.__dict__:
                # might not yet be sliced, but loaded into its host
                if name not in snap.get_host_subsnap(name).__dict__:
                    continue
            if environment.verbose:
                print 'apply %s to "%s" of %s...' % (self.__class__.__name__,
                                                     name, snap.descriptor),
                sys.stdout.flush()
            self._change[name](name,snap)
            if environment.verbose:
                print 'done.'
                sys.stdout.flush()
            done.add(name)

        if fams:
            for fam in [getattr(snap,fn) for fn in snap.families()]:
                # fams=True would result in infinite recursion
                # exclude=done prevents multiple applications on (partial) blocks
                # total=True would overwrite snap=fam
                # remember=True would not be effectual, since snap!=root
                self.apply(fam, total=False, remember=False, fams=False,
                           exclude=done)

        if remember and snap is snap.root:
            if snap._trans_at_load and type(snap._trans_at_load[-1])==type(self):
                last = snap._trans_at_load[-1]
                if isinstance(self, Translation):
                    trans = self._trans.copy()
                    if trans.units is None:
                        trans.units = snap.boxsize.units
                    last._trans += trans.in_units_of(last._trans.units,subs=snap)
                elif isinstance(self, Rotation):
                    last._R = self._R * last._R
                else:
                    raise NotImplementedError('Encountered an unknown '
                                              'transformation: %s' %
                                              self.__class__.__name__)
            else:
                if isinstance(self, Translation) and self._trans.units is None:
                    self._trans.units = snap.boxsize.units
                snap._trans_at_load.append( self.copy() )

class Translation(Transformation):
    '''
    A translation (in space).

    Args:
        trans (UnitQty):    The translation vector.
    '''

    def __init__(self, trans):
        # velocities are peculiar, hence already correct
        super(Translation,self).__init__( {
                    'pos':  self._apply_to_block,
                })
        self.trans = trans

    @property
    def trans(self):
        return self._trans.copy()

    @trans.setter
    def trans(self, value):
        self._trans = UnitQty(value).astype(float).copy()
        if self._trans.shape != (3,):
            raise ValueError('The translation vector needs to be a 3-vector!')

    def copy(self):
        '''Copy the translation.'''
        return Translation(self._trans)

    def inverse(self):
        '''Calculate the inverse translation.'''
        return Translation(-self._trans)

    def __str__(self):
        unit_str = ' %s'%self._trans.units if self._trans.units else ''
        return 'Translation([%.4g,%.4g,%.4g]%s)'%(tuple(self._trans)+(unit_str,))

    def _apply_to_block(self, block, snap=None):
        if snap is not None:
            block = getattr(snap,block)
        if not len(block.shape)==2 and block.shape[1]==self._trans.shape[0]:
            raise ValueError('The block has to have shape (?,%d)!' %
                    self._trans.shape[0])

        if snap is None:
            block = block + self._trans
        else:
            block += self._trans.in_units_of(block.units,subs=snap)
        return block

class Rotation(Transformation):
    '''
    A spatial rotation.

    Args:
        rotmat (array-like):    The rotation matrix (has to fullfil R.T*R==1).
        test_proper (bool):     Test for a proper rotation (i.e. det(R) = +1) on
                                initialization and whenever the rotation matrix is
                                changed.
    '''

    def __init__(self, rotmat, test_proper=True):
        super(Rotation,self).__init__( {
                    'pos':  self._apply_to_block,
                    'vel':  self._apply_to_block,
                    'acce': self._apply_to_block,
                } )
        self.test_proper = test_proper
        self.rotmat = rotmat

    @property
    def rotmat(self):
        return self._R.copy()

    @rotmat.setter
    def rotmat(self, value):
        self._R = np.matrix(value, dtype=float).copy()
        if len(self._R.shape)!=2 or self._R.shape!=(3,3):
            raise ValueError('Rotation matrix needs to be a 3x3-matrix!')
        if np.sum(np.abs( (self._R * self._R.T) - np.eye(3) )) > 1e-6:
            raise ValueError('Rotation matrix needs to fullfil R^T == R^-1!')
        if self._test_proper and not self.is_proper():
            raise ValueError('Rotation matrix needs to fullfil det(R) == +1 '
                             '(proper Rotation)!')

    @property
    def test_proper(self):
        return self._test_proper

    @test_proper.setter
    def test_proper(self, value):
        self._test_proper = bool(value)

    def is_proper(self):
        '''Test if the rotation is a proper rotation, i.e. it perserves
        chirality.'''
        return np.linalg.det(self._R) > 0.0

    def axis(self):
        '''Calculate the axis around which the rotation is performed.'''
        vals, vecs = np.linalg.eig(self._R)
        i = np.where(np.abs(vals-1) < 1e-9)[0][0]
        return vecs[:,i].real.getA1()

    def angle(self):
        '''Calculate the angle of the rotation.'''
        return np.arccos((np.trace(self._R) - 1.0) / 2.0)

    def copy(self):
        '''Copy the rotation.'''
        return Rotation(self._R)

    def inverse(self):
        '''Calculate the inverse rotation.'''
        return Rotation(self._R.T)  # remember: R^T == R^-1

    def __str__(self):
        mat = ''
        for i in range(3):
            mat += ',[%6.3f,%6.3f,%6.3f]' % (self._R[i,0],self._R[i,1],self._R[i,2])
        mat = '[%s]' % mat.strip(',')
        return 'Rotation(%s)' % mat

    def _apply_to_block(self, block, snap=None):
        if snap is not None:
            name, block = block, getattr(snap,block)
        if not len(block.shape)==2 and block.shape[1]==self._R.shape[0]:
            raise ValueError('The block has to have shape (?,%d)!' %
                    self._R.shape[0])

        transformed = (self._R * block.T).T.view(type(block))

        if isinstance(block, UnitArr):
            transformed.units = block.units
            transformed = transformed.view(UnitArr) # downgrade if SimArr

        if snap is not None:
            block[:] = transformed
        return transformed

def rot_from_axis_angle(u, angle):
    '''
    Create a Rotation of an angle around a axis.

    Args:
        u (array-like):         The axis to rotate around (does not have to be
                                normalized).
        angle (UnitScalar):     The angle in radians around the axis u (right-hand
                                rotation). (Default units: rad)

    Example:
        >>> print rot_from_axis_angle([1,0,0], np.pi/2.0)
        Rotation([[ 1.000, 0.000, 0.000],[ 0.000, 0.000,-1.000],[ 0.000, 1.000, 0.000]])
        >>> print rot_from_axis_angle([0,0,1], np.pi/4.0)
        Rotation([[ 0.707,-0.707, 0.000],[ 0.707, 0.707, 0.000],[ 0.000, 0.000, 1.000]])
        >>> print rot_from_axis_angle([0,0,1], '12 degree')
        Rotation([[ 0.978,-0.208, 0.000],[ 0.208, 0.978, 0.000],[ 0.000, 0.000, 1.000]])
        >>> R = rot_from_axis_angle([1,2,3], 1.234)
        >>> np.sqrt(1**2+2**2+3**2)*R.axis(), R.angle()
        (array([ 1.,  2.,  3.]), 1.234)
    '''
    if isinstance(angle, (str,UnitArr)):
        angle = UnitScalar(angle, 'rad')
    angle = float(angle)
    u = np.array(u, dtype=float)
    if u.shape != (3,):
        raise ValueError('The axis has to be a 3-vector.')
    norm = np.linalg.norm(u)
    if norm == 0:
        raise ValueError('The axis may not have zero norm!')
    u /= norm

    cos_a, sin_a = np.cos(angle), np.sin(angle)
    uxu = np.tensordot(u,u,0)
    u_x = np.array([[0,-u[2],u[1]],[u[2],0,-u[0]],[-u[1],u[0],0]])

    return Rotation(cos_a*np.eye(3)+sin_a*u_x+(1.0-cos_a)*uxu)

def rot_to_z(z):
    '''
    Calculate a rotation such that the new z-axis is the defined one.

    Args:
        z (array-like): The vector defining the new z-axis. (Does not have to be
                        normalized.)

    >>> assert np.all(rot_to_z([0,0,1]).rotmat == np.eye(3))
    >>> z = rot_to_z([1,2,3]).apply_to_block(np.array([[1,2,3]]))
    >>> assert abs(z[0,0])<1e-9 and abs(z[0,1])<1e-9
    >>> print rot_to_z([0,1,1])
    Rotation([[ 1.000, 0.000, 0.000],[ 0.000, 0.707,-0.707],[ 0.000, 0.707, 0.707]])
    >>> print rot_to_z([0.5,-1,0])
    Rotation([[ 0.800, 0.400,-0.447],[ 0.400, 0.200, 0.894],[ 0.447,-0.894, 0.000]])
    '''
    z = np.array(z,dtype=float)
    if z.shape != (3,):
        raise ValueError('The new z axis has to be defined by a 3-vector.')
    norm = np.linalg.norm(z)
    if norm == 0:
        raise ValueError('The axis may not have zero norm!')
    z /= norm

    # get shortest rotation
    u = np.cross(z,[0,0,1])
    angle = np.arccos(z[2])

    if np.linalg.norm(u) < 1e-10:
        return Rotation(np.eye(3))

    return rot_from_axis_angle(u,angle)


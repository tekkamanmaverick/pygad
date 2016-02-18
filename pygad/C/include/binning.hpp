#pragma once
#include "general.hpp"
#include "kernels.hpp"
#include "looploop.hpp"

extern double H_lim_out_of_grid;

extern "C"
void sph_bin_3D(size_t N,
                double *pos,
                double *hsml,
                double *dV,
                double *qty,
                double *extent,
                size_t Npx[3],
                double *grid,
                const char *kernel_,
                double periodic);

extern "C"
void sph_3D_bin_2D(size_t N,
                   double *pos,
                   double *hsml,
                   double *dV,
                   double *qty,
                   double *extent,
                   size_t Npx[2],
                   double *grid,
                   const char *kernel_,
                   double periodic);


// Mind the reversed indexing of i_min, i_max, and i due to performace at accessing
// array elements in reversed loop order in nested_loops<2>::do_loops(...)!
// Index n in i,i_min,i_max is index k=(d-1)-n for grid_r, Npx, res, etc... (and
// vice versa).

// helper funktion templates
template <int d>
bool out_of_grid(const size_t *i, const size_t *Npx) {
    for (int k=0; k<d; k++) {
        if (i[(d-1)-k]<0 or Npx[k]<=i[(d-1)-k])
            return true;
    }
    return false;
}
template <int d>
bool extents_out_of_grid(const size_t *i_min, const size_t *i_max, const size_t *Npx) {
    for (int n=0; n<d; n++) {
        if (i_min[n]==0 or i_max[n]==Npx[(d-1)-n])
            return true;
    }
    return false;
}
template <int d>
inline size_t construct_linear_idx(const size_t *i, const size_t *Npx) {
    size_t I = i[(d-1)-0];
    for (int k=1; k<d; k++)
        I = I*Npx[k] + i[(d-1)-k];
    return I;
}
// end of helper funktion templates

template <int d, bool projected=false>
void bin_sph(size_t N,
             double *pos,
             double *hsml,
             double *dV,
             double *qty,
             double *extent,
             size_t Npx[d],
             double *grid,
             const char *kernel_,
             double periodic) {
    //printf("initialze kernel...\n");
    Kernel<(projected ? d+1 : d)> kernel(kernel_);
    if (projected) {
        kernel.generate_projection(1024);
    }

    //printf("initizalize grid...\n");
    size_t Ngrid = Npx[0];
    for (int k=1; k<d; k++)
        Ngrid *= Npx[k];
    memset(grid, 0, Ngrid*sizeof(double));
    assert(grid[Ngrid-1]==0.0);

    //auto t_start = std::chrono::high_resolution_clock::now();

    //printf("bin %zu particles %son %dD grid...\n", N, (projected ? "(projected) ": ""), d);
    double res[d];
    for (int k=0; k<d; k++)
        res[k] = (extent[2*k+1]-extent[2*k]) / Npx[k];
    double res_min = res[0];
    for (int k=1; k<d; k++)
        res_min = std::min(res_min, res[k]);
    double dV_px = res[0];
    for (int k=1; k<d; k++)
        dV_px *= res[k];
#pragma omp parallel for default(shared) schedule(dynamic,10)
    for (size_t j=0; j<N; j++) {
        double *rj = pos+(d*j);
        double hj = hsml[j];
        double dVj = dV[j];
        double Qj = qty[j];

        // Mind the reversed indexing of i_min, i_max, and i due to performace
        // at accessing array elements in reversed loop order in
        // nested_loops<d>::do_loops(...)!
        size_t i_min[d], i_max[d];
        for (int k=0; k<d; k++) {
            i_min[(d-1)-k] = std::max<double>( (rj[k]-extent[2*k]-hj) / res[k],       0.0);
            i_min[(d-1)-k] = std::min(i_min[(d-1)-k], Npx[k]);
            i_max[(d-1)-k] = std::min<size_t>( (rj[k]-extent[2*k]+hj) / res[k] + 1.0, Npx[k]);
        }

        double W_int;
        // no correction for particles that extent out of the grid and the
        // integral is not over the entire kernel
        if (hj > H_lim_out_of_grid*res_min and extents_out_of_grid<d>(i_min, i_max, Npx)) {
            W_int = 1.0;
        } else {
            W_int = 0.0;
            size_t i[d];
            double grid_r[d];
            nested_loops<d>::do_loops(i, i_min, i_max,
                [&](unsigned n, size_t *i, size_t *i_min, size_t *i_max){
                    const unsigned k = (d-1)-n;
                    grid_r[k] = extent[2*k] + (i[n]+0.5)*res[k];
                },
                [&](unsigned n, size_t *i, size_t *i_min, size_t *i_max){
                    const unsigned k = (d-1)-n;
                    grid_r[k] = extent[2*k] + (i[n]+0.5)*res[k];
                    double dj = dist_periodic<d>(grid_r, rj, periodic);
                    if (projected)
                        W_int += dV_px * kernel.proj_value(dj/hj, hj);
                    else
                        W_int += dV_px * kernel.value(dj/hj, hj);
            });
        }

        if (W_int<1e-4) {
            // Mind the reversed indexing of i_min, i_max, and i due to performace
            // at accessing array elements in reversed loop order in
            // nested_loops<d>::do_loops(...)!
            size_t i[d];
            for (int k=0; k<d; k++)
                i[(d-1)-k] = (rj[k]-extent[2*k]) / res[k];
            // dismiss if out of grid
            if ( out_of_grid<d>(i, Npx) )
                continue;
            size_t I = construct_linear_idx<d>(i, Npx);
            double VV = dVj / dV_px;
#pragma omp atomic
            grid[I] += VV * Qj;
        } else {
            size_t i[d];
            double grid_r[d];
            nested_loops<d>::do_loops(i, i_min, i_max,
                [&](unsigned n, size_t *i, size_t *i_min, size_t *i_max){
                    const unsigned k = (d-1)-n;
                    grid_r[k] = extent[2*k] + (i[n]+0.5)*res[k];
                },
                [&](unsigned n, size_t *i, size_t *i_min, size_t *i_max){
                    const unsigned k = (d-1)-n;
                    grid_r[k] = extent[2*k] + (i[n]+0.5)*res[k];
                    size_t I = construct_linear_idx<d>(i, Npx);
                    double dj = dist_periodic<d>(grid_r, rj, periodic);
                    double dVj_Wj;
                    if (projected)
                        dVj_Wj = dVj / W_int * kernel.proj_value(dj/hj, hj);
                    else
                        dVj_Wj = dVj / W_int * kernel.value(dj/hj, hj);
#pragma omp atomic
                    grid[I] += dVj_Wj * Qj;
            });
        }
    }

    /*
    auto t_end = std::chrono::high_resolution_clock::now();
    auto diff = std::chrono::duration_cast<std::chrono::duration<double>>(t_end-t_start);
    printf("binning %son %dD grid took %.6f s\n", (projected ? "(projected) ": ""), d, diff.count());
    */
}


use pyo3::prelude::*;
use pyo3::types::PyDict;
use std::collections::BTreeMap;

const CENTER_MERGE_EPSILON: f64 = 2.0;
const MIN_BAND_WIDTH: f64 = 5.0;

#[pyfunction]
fn y_cluster(points: Vec<f64>, bin_px: i32) -> PyResult<Vec<f64>> {
    if points.is_empty() {
        return Ok(Vec::new());
    }

    let bin_size = if bin_px <= 0 {
        1.0
    } else {
        bin_px as f64
    };

    let mut clusters: BTreeMap<i64, Vec<f64>> = BTreeMap::new();
    for value in points {
        if !value.is_finite() {
            continue;
        }
        let key = (value / bin_size).round() as i64;
        clusters.entry(key).or_default().push(value);
    }

    let mut centers: Vec<f64> = clusters
        .into_iter()
        .filter_map(|(_, values)| {
            if values.is_empty() {
                None
            } else {
                let sum: f64 = values.iter().copied().sum();
                Some(sum / values.len() as f64)
            }
        })
        .collect();

    centers.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    centers.dedup_by(|a, b| (a - b).abs() <= f64::EPSILON);
    Ok(centers)
}

#[pyfunction]
fn stitch_bp(lines: Vec<String>) -> PyResult<Option<String>> {
    if lines.len() < 2 {
        return Ok(None);
    }

    for (index, line) in lines.iter().enumerate() {
        let trimmed: String = line.chars().filter(|c| !c.is_whitespace()).collect();
        if trimmed.len() < 2 || !trimmed.ends_with('/') {
            continue;
        }
        let prefix = &trimmed[..trimmed.len() - 1];
        if prefix.len() < 2 || prefix.len() > 3 || !prefix.chars().all(|c| c.is_ascii_digit()) {
            continue;
        }

        for candidate in lines.iter().skip(index + 1) {
            let digits: String = candidate.chars().filter(|c| !c.is_whitespace()).collect();
            if digits.len() < 2 || digits.len() > 3 || !digits.chars().all(|c| c.is_ascii_digit()) {
                continue;
            }
            return Ok(Some(format!("{}/{}", prefix, digits)));
        }
    }

    Ok(None)
}

#[pyfunction]
fn select_bands(py: Python<'_>, centers: Vec<(i32, f64)>, page_w: f64) -> PyResult<Py<PyDict>> {
    if centers.is_empty() {
        return Ok(PyDict::new(py).into());
    }

    let mut per_day: BTreeMap<i32, Vec<f64>> = BTreeMap::new();
    for (day, center) in centers {
        if !center.is_finite() {
            continue;
        }
        per_day.entry(day).or_default().push(center);
    }

    let mut averaged: Vec<(i32, f64)> = per_day
        .into_iter()
        .filter_map(|(day, values)| {
            if values.is_empty() {
                None
            } else {
                let sum: f64 = values.iter().copied().sum();
                Some((day, sum / values.len() as f64))
            }
        })
        .collect();

    averaged.sort_by(|a, b| a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal));

    let mut merged: Vec<(i32, f64)> = Vec::new();
    if let Some(first) = averaged.first().cloned() {
        let mut group: Vec<(i32, f64)> = vec![first];
        for entry in averaged.into_iter().skip(1) {
            if let Some((_, last_center)) = group.last() {
                if (entry.1 - *last_center).abs() <= CENTER_MERGE_EPSILON {
                    group.push(entry);
                } else {
                    merged.extend(collapse_center_group(&group));
                    group = vec![entry];
                }
            }
        }
        merged.extend(collapse_center_group(&group));
    }

    let mut bands: Vec<(i32, (f64, f64))> = Vec::new();
    let count = merged.len();
    for (index, (day, center_x)) in merged.iter().enumerate() {
        let mut x0;
        let mut x1;
        if count == 1 {
            x0 = 0.0;
            x1 = page_w;
        } else if index == 0 {
            let next_center = merged.get(index + 1).map(|(_, c)| *c).unwrap_or(*center_x);
            let delta = (next_center - *center_x) / 2.0;
            x0 = *center_x - delta;
            x1 = *center_x + delta;
        } else if index == count - 1 {
            let prev_center = merged.get(index - 1).map(|(_, c)| *c).unwrap_or(*center_x);
            let delta = (*center_x - prev_center) / 2.0;
            x0 = *center_x - delta;
            x1 = *center_x + delta;
        } else {
            let prev_center = merged.get(index - 1).map(|(_, c)| *c).unwrap_or(*center_x);
            let next_center = merged.get(index + 1).map(|(_, c)| *c).unwrap_or(*center_x);
            x0 = *center_x - (*center_x - prev_center) / 2.0;
            x1 = *center_x + (next_center - *center_x) / 2.0;
        }

        x0 = x0.max(0.0);
        x1 = x1.min(page_w);
        if x1 < x0 {
            let tmp = x0;
            x0 = x1;
            x1 = tmp;
        }

        let width = x1 - x0;
        if width < MIN_BAND_WIDTH || x1 <= x0 {
            continue;
        }
        bands.push((*day, (x0, x1)));
    }

    let dict = PyDict::new(py);
    for (day, (x0, x1)) in bands {
        dict.set_item(day, (x0, x1))?;
    }
    Ok(dict.into())
}

fn collapse_center_group(group: &[(i32, f64)]) -> Vec<(i32, f64)> {
    if group.is_empty() {
        return Vec::new();
    }
    if group.len() == 1 {
        return group.to_vec();
    }
    let first_day = group[0].0;
    let single_day = group.iter().all(|(day, _)| *day == first_day);
    if single_day {
        let avg = group.iter().map(|(_, value)| *value).sum::<f64>() / group.len() as f64;
        vec![(first_day, avg)]
    } else {
        group.to_vec()
    }
}

#[pymodule]
fn hushdesk_accel(py: Python<'_>, module: &PyModule) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(y_cluster, module)?)?;
    module.add_function(wrap_pyfunction!(stitch_bp, module)?)?;
    module.add_function(wrap_pyfunction!(select_bands, module)?)?;
    Ok(())
}

import numpy as np
import math
import csv
import pandas as pd
from scipy.stats import chi2
# Define lists to store results
r = []
el = []
az = []
class CVFilter:
    def __init__(self):
        self.Sf = np.zeros((6, 1))  # Filter state vector
        self.Pf = np.eye(6)  # Filter state covariance matrix
        self.Sp = np.zeros((6, 1))  # Predicted state vector
        self.Pp = np.eye(6)  # Predicted state covariance matrix
        self.plant_noise = 20  # Plant noise covariance
        self.H = np.eye(3, 6)  # Measurement matrix
        self.R = np.eye(3)  # Measurement noise covariance
        self.Meas_Time = 0  # Measured time
        self.prev_Time = 0
        self.Q = np.eye(6)
        self.Phi = np.eye(6)
        self.Z = np.zeros((3, 1)) 
        self.Z1 = np.zeros((3, 1))  # Measurement vector
        self.Z2 = np.zeros((3, 1)) 
        self.first_rep_flag = False
        self.second_rep_flag = False
        self.gate_threshold = 9.21  # 95% confidence interval for Chi-square distribution with 3 degrees of freedom

    def initialize_filter_state(self, x, y, z, vx, vy, vz, time):
        if not self.first_rep_flag:
            self.Z1 = np.array([[x], [y], [z]])
            self.Sf[0] = x
            self.Sf[1] = y
            self.Sf[2] = z
            self.Meas_Time = time
            self.prev_Time = self.Meas_Time
            self.first_rep_flag = True
        elif self.first_rep_flag and not self.second_rep_flag:
            self.Z2 = np.array([[x], [y], [z]])
            self.prev_Time = self.Meas_Time
            self.Meas_Time = time
            dt = self.Meas_Time - self.prev_Time
            self.vx = (self.Z1[0] - self.Z2[0]) / dt
            self.vy = (self.Z1[1] - self.Z2[1]) / dt
            self.vz = (self.Z1[2] - self.Z2[2]) / dt
            self.Meas_Time = time
            self.second_rep_flag = True
        else:
            self.Z = np.array([[x], [y], [z]])
            self.prev_Time = self.Meas_Time
            self.Meas_Time = time
    def predict_step(self, current_time):
        dt = current_time - self.prev_Time
        T_2 = (dt * dt) / 2.0
        T_3 = (dt * dt * dt) / 3.0
        self.Phi[0, 3] = dt
        self.Phi[1, 4] = dt
        self.Phi[2, 5] = dt              
        self.Q[0, 0] = T_3
        self.Q[1, 1] = T_3
        self.Q[2, 2] = T_3
        self.Q[0, 3] = T_2
        self.Q[1, 4] = T_2
        self.Q[2, 5] = T_2
        self.Q[3, 0] = T_2
        self.Q[4, 1] = T_2
        self.Q[5, 2] = T_2
        self.Q[3, 3] = dt
        self.Q[4, 4] = dt
        self.Q[5, 5] = dt
        self.Q = self.Q * self.plant_noise
        self.Sp = np.dot(self.Phi, self.Sf)
        self.Pp = np.dot(np.dot(self.Phi, self.Pf), self.Phi.T) + self.Q
        self.Meas_Time = current_time

    def update_step(self, Z):
        Inn = Z - np.dot(self.H, self.Sp)
        S = np.dot(self.H, np.dot(self.Pp, self.H.T)) + self.R
        K = np.dot(np.dot(self.Pp, self.H.T), np.linalg.inv(S))
        self.Sf = self.Sp + np.dot(K, Inn)
        self.Pf = np.dot(np.eye(6) - np.dot(K, self.H), self.Pp)


def read_measurements_from_csv(file_path):
    measurements = []
    with open(file_path, 'r') as file:
        reader = csv.reader(file)
        next(reader)  # Skip header if exists
        for row in reader:
            mr = float(row[7])  # MR column
            ma = float(row[8])  # MA column
            me = float(row[9])  # ME column
            mt = float(row[10])  # MT column
            md = float(row[11])
            x, y, z = sph2cart(ma, me, mr)  # Convert spherical to Cartesian coordinates
            measurements.append((mr, ma, me, mt, md, x, y, z))
    return measurements


def sph2cart(az, el, r):
    x = r * np.cos(el * np.pi / 180) * np.sin(az * np.pi / 180)
    y = r * np.cos(el * np.pi / 180) * np.cos(az * np.pi / 180)
    z = r * np.sin(el * np.pi / 180)
    return x, y, z


def cart2sph(x, y, z):
    r = np.sqrt(x**2 + y**2 + z**2)
    el = math.atan2(z, np.sqrt(x**2 + y**2)) * 180 / np.pi
    az = math.atan2(y, x)

    if x > 0.0:
        az = np.pi / 2 - az
    else:
        az = 3 * np.pi / 2 - az

    az = az * 180 / np.pi
    if az < 0.0:
        az = 360 + az
    if az > 360:
        az = az - 360
    return r, az, el


def form_measurement_groups(measurements, max_time_diff=0.050):
    measurement_groups = []
    current_group = []
    base_time = measurements[0][3]

    for measurement in measurements:
        if measurement[3] - base_time <= max_time_diff:
            current_group.append(measurement)
        else:
            measurement_groups.append(current_group)
            current_group = [measurement]
            base_time = measurement[3]

    if current_group:
        measurement_groups.append(current_group)

    return measurement_groups


def form_clusters_via_association(tracks, reports, kalman_filter, chi2_threshold):
    association_list = []
    cov_inv = np.linalg.inv(kalman_filter.Pp[:3, :3])  # 3x3 covariance matrix for position only

    for i, track in enumerate(tracks):
        for j, report in enumerate(reports):
            distance = mahalanobis_distance(track, report, cov_inv)
            if distance < chi2_threshold:
                association_list.append((i, j))

    clusters = []
    while association_list:
        cluster_tracks = set()
        cluster_reports = set()
        stack = [association_list.pop(0)]
        
        while stack:
            track_idx, report_idx = stack.pop()
            cluster_tracks.add(track_idx)
            cluster_reports.add(report_idx)
            new_assoc = [(t, r) for t, r in association_list if t == track_idx or r == report_idx]
            for assoc in new_assoc:
                if assoc not in stack:
                    stack.append(assoc)
            association_list = [assoc for assoc in association_list if assoc not in new_assoc]
        
        clusters.append((list(cluster_tracks), [reports[r] for r in cluster_reports]))

    return clusters


def mahalanobis_distance(track, report, cov_inv):
    residual = np.array(report) - np.array(track)
    distance = np.dot(np.dot(residual.T, cov_inv), residual)
    return distance


def select_best_report(cluster_tracks, cluster_reports, kalman_filter):
    cov_inv = np.linalg.inv(kalman_filter.Pp[:3, :3])

    best_report = None
    best_track_idx = None
    max_weight = -np.inf

    for i, track in enumerate(cluster_tracks):
        for j, report in enumerate(cluster_reports):
            residual = np.array(report) - np.array(track)
            weight = np.exp(-0.5 * np.dot(np.dot(residual.T, cov_inv), residual))
            if weight > max_weight:
                max_weight = weight
                best_report = report
                best_track_idx = i

    return best_track_idx, best_report

def select_initiation_mode(mode):
    if mode == '3-state':
        return 3
    elif mode == '5-state':
        return 5
    elif mode == '7-state':
        return 7
    else:
        raise ValueError("Invalid mode selected.")
    
    
def doppler_correlation(doppler_1, doppler_2, doppler_threshold):
    return abs(doppler_1 - doppler_2) < doppler_threshold

def initialize_tracks(measurement_groups, doppler_threshold, range_threshold, firm_threshold, mode):
    tracks = []
    track_id_list = []
    hit_counts = {}
    miss_counts = {}
    tentative_ids = {}
    firm_ids = set()
    state_map = {}
    firm_threshold = select_initiation_mode(mode)

    state_progression = {
        3: ['Poss1', 'Tentative1', 'Firm'],
        5: ['Poss1', 'Poss2', 'Tentative1', 'Tentative2', 'Firm'],
        7: ['Poss1', 'Poss2', 'Tentative1', 'Tentative2', 'Tentative3', 'Firm']
    }
    progression_states = state_progression[firm_threshold]

    for group in measurement_groups:
        measurement_cartesian = sph2cart(group[0][0], group[0][1], group[0][2])
        measurement_doppler = group[0][3]

        assigned = False

        for track_id, track in enumerate(tracks):
            if not track:
                continue

            last_measurement = track['measurements'][-1][0]
            last_cartesian = sph2cart(last_measurement[0], last_measurement[1], last_measurement[2])
            last_doppler = last_measurement[3]
            distance = np.linalg.norm(np.array(measurement_cartesian) - np.array(last_cartesian))

            doppler_correlated = doppler_correlation(measurement_doppler, last_doppler, doppler_threshold)
            range_satisfied = distance < range_threshold
            
            if doppler_correlated and range_satisfied :
                hit_counts[track_id] = hit_counts.get(track_id, 0) + 1
                
                # Determine state based on hit count
                if hit_counts[track_id] == 1:
                    state_map[track_id] = progression_states[0]  # Poss1
                elif hit_counts[track_id] == 2:
                    state_map[track_id] = progression_states[1]  # Tentative1
                elif hit_counts[track_id] >= 3:
                    state_map[track_id] = progression_states[2]  # Firm
                    firm_ids.add(track_id)

                track['measurements'].append((group[0], state_map[track_id]))
                track['current_state'] = state_map[track_id]
                assigned = True
                break

        if not assigned:
            new_track_id = len(track_id_list) + 1
            tracks.append({
                'track_id': new_track_id,
                'measurements': [(group[0], progression_states[0])],
                'current_state': progression_states[0]
            })
            track_id_list.append({'id': new_track_id, 'state': 'occupied'})
            hit_counts[new_track_id] = 1  # First hit
            state_map[new_track_id] = progression_states[0]

    return tracks, track_id_list, miss_counts, hit_counts, firm_ids, state_map, progression_states

def main():
    file_path = 'ttk.csv'
    measurements = read_measurements_from_csv(file_path)

    kalman_filter = CVFilter()
    measurement_groups = form_measurement_groups(measurements, max_time_diff=0.050)

    tracks = []
    track_id_list = []
    filter_states = []

    doppler_threshold = 100
    range_threshold = 100
    firm_threshold = 3
    mode = '3-state'

    firm_threshold = select_initiation_mode(mode)
    # Initialize variables outside the loop
    miss_counts = {}
    hit_counts = {}
    firm_ids = set()
    state_map = {}
    progression_states = {
        3: ['Poss1', 'Tentative1', 'Firm'],
        5: ['Poss1', 'Poss2', 'Tentative1', 'Tentative2', 'Firm'],
        7: ['Poss1', 'Poss2', 'Tentative1', 'Tentative2', 'Tentative3', 'Firm']
    }[firm_threshold]

    for group_idx, group in enumerate(measurement_groups):
        print(f"Processing measurement group {group_idx + 1}...")

        current_measurement_group = [group]
        current_tracks, current_track_id_list, current_miss_counts, current_hit_counts, current_firm_ids, current_state_map, current_progression_states = initialize_tracks(
            current_measurement_group, doppler_threshold, range_threshold, firm_threshold, mode)

        # Merge current tracks with existing tracks
        for ct in current_tracks:
            tracks.append(ct)
        track_id_list.extend(current_track_id_list)
        hit_counts.update(current_hit_counts)
        miss_counts.update(current_miss_counts)
        firm_ids.update(current_firm_ids)
        state_map.update(current_state_map)

        if len(group) > 1:  # Multiple measurements in the group
            tracks_in_group = []
            reports = []

            for i, (rng, azm, ele, mt, md,*rest) in enumerate(group):
                print(f"\nMeasurement {i + 1}: (az={azm}, el={ele}, r={rng}, t={mt}), md={md}\n")
                x, y, z = sph2cart(azm, ele, rng)
                reports.append((x, y, z))

                for track_id, track in enumerate(tracks):
                    if not track:
                        continue

                    current_state = state_map.get(track_id, None)
                    print(f"Track {track_id} is in state: {current_state}")

                    if current_state == 'free':
                        state_map[track_id] = 'unknown'
                        track['current_state'] = 'unknown'
                        print(f"Track {track_id} state set to 'unknown'.")

                    if current_state == 'Poss1':
                        if track_id not in firm_ids:
                            print("Track in 'Poss1' state, initializing filter...")
                            kalman_filter.initialize_filter_state(x, y, z, 0, 0, 0, mt)
                            track['Sf'] = kalman_filter.Sf.copy()
                            track['Pf'] = kalman_filter.Pf.copy()
                            track['Pp'] = kalman_filter.Pp.copy()
                            track['Sp'] = kalman_filter.Sp.copy()
                            track.setdefault('times', []).append((mt, (x, y, z)))  # Track time and measurement
                    elif current_state == 'Tentative1':
                        if track_id not in firm_ids:
                            print("Track in 'Tentative' state, performing prediction and update...")
                            kalman_filter.predict_step(mt)
                            Z = np.array([[x], [y], [z]])
                            kalman_filter.update_step(Z)
                            print("Updated filter state:", kalman_filter.Sf.flatten())
                            track['Sf'] = kalman_filter.Sf.copy()
                            track['Pf'] = kalman_filter.Pf.copy()
                            track['Pp'] = kalman_filter.Pp.copy()
                            track['Sp'] = kalman_filter.Sp.copy()
                            track.setdefault('times', []).append((mt, (x, y, z)))  # Track time and measurement
                    elif current_state == 'Firm':
                        print("Track in 'Firm' state, performing prediction and update...")
                        kalman_filter.predict_step(mt)
                        Z = np.array([[x], [y], [z]])
                        kalman_filter.update_step(Z)
                        print("Updated filter state:", kalman_filter.Sf.flatten())
                        track['Sf'] = kalman_filter.Sf.copy()
                        track['Pf'] = kalman_filter.Pf.copy()
                        track['Pp'] = kalman_filter.Pp.copy()
                        track['Sp'] = kalman_filter.Sp.copy()
                        track.setdefault('times', []).append((mt, (x, y, z)))  # Track time and measurement

                tracks_in_group.append(kalman_filter.Sf[:3].flatten())

            clusters = form_clusters_via_association(tracks_in_group, reports, kalman_filter, chi2_threshold=kalman_filter.gate_threshold)
            print("Clusters formed:", clusters)

            for cluster_tracks, cluster_reports in clusters:
                if cluster_tracks and cluster_reports:
                    best_track_idx, best_report = select_best_report(cluster_tracks, cluster_reports, kalman_filter)
                    if best_report is not None:
                        print(f"Selected Best Report for Track {best_track_idx + 1}: {best_report}")
                        Z = np.array([[best_report[0]], [best_report[1]], [best_report[2]]])
                        kalman_filter.update_step(Z)
                        print("Updated filter state:", kalman_filter.Sf.flatten())
                        r_val, az_val, el_val = cart2sph(kalman_filter.Sf[0], kalman_filter.Sf[1], kalman_filter.Sf[2])
                        filter_states.append(kalman_filter.Sf.flatten())

                        # Update hit counts
                        if best_track_idx is not None and 0 <= best_track_idx < len(hit_counts):
                            hit_counts[best_track_idx] += 1
                        else:
                            print(f"Invalid best_track_idx: {best_track_idx}")
                        miss_counts[best_track_idx] = 0

        else:  # Single measurement in the group
            rng, azm, ele, mt, md,*rest = group[0]
            print(f"\nSingle Measurement: (az={azm}, el={ele}, r={rng}, t={mt}), md={md}\n")
            x, y, z = sph2cart(azm, ele, rng)

            assigned = False
            for track_id, track in enumerate(tracks):
                if not track:
                    continue

                current_state = state_map.get(track_id, None)
                print(f"Track {track_id} is in state: {current_state}")

                if current_state == 'free':
                    state_map[track_id] = 'unknown'
                    track['current_state'] = 'unknown'
                    print(f"Track {track_id} state set to 'unknown'.")

                if current_state == 'Poss1' or current_state == 'Tentative1':
                    distance = np.linalg.norm(np.array([x, y, z]) - np.array(track['measurements'][-1][0][5:8]))
                    if distance < range_threshold:
                        print("Assigning measurement to track.")
                        kalman_filter.predict_step(mt)
                        Z = np.array([[x], [y], [z]])
                        kalman_filter.update_step(Z)
                        assigned = True
                        track['Sf'] = kalman_filter.Sf.copy()
                        track['Pf'] = kalman_filter.Pf.copy()
                        track['Pp'] = kalman_filter.Pp.copy()
                        track['Sp'] = kalman_filter.Sp.copy()

                        new_state = progression_states[min(progression_states.index(current_state) + 1, len(progression_states) - 1)]
                        track['current_state'] = new_state
                        track['measurements'].append((group[0], new_state))
                        
                        # Update hit counts
                        hit_counts[track_id] += 1
                        miss_counts[track_id] = 0
                        break

            if not assigned:
                free_track_idx = next((i for i, track in enumerate(track_id_list) if track['state'] == 'free'), None)
                if free_track_idx is not None:
                    new_track_id = track_id_list[free_track_idx]['id']
                    tracks.append({
                        'track_id': new_track_id,
                        'measurements': [(group[0], 'Poss1')],
                        'Sf': np.zeros((6, 1)),
                        'Pf': np.eye(6),
                        'Pp': np.eye(6),
                        'Sp': np.zeros((6, 1)),
                        'current_state': 'Poss1'
                    })
                    track_id_list[free_track_idx]['state'] = 'occupied'
                    kalman_filter.initialize_filter_state(x, y, z, 0, 0, 0, mt)
                    track['Sf'] = kalman_filter.Sf.copy()
                    track['Pf'] = kalman_filter.Pf.copy()
                    track['Pp'] = kalman_filter.Pp.copy()
                    track['Sp'] = kalman_filter.Sp.copy()
                    hit_counts[new_track_id] = 1
                    miss_counts[new_track_id] = 0
                else:
                    print("No available tracks to assign measurement.")

    # Summary generation
    for track_id, track in enumerate(tracks):
        if track:
            # Ensure keys exist to prevent KeyError
            track.setdefault('Sf', np.zeros((6, 1)))
            track.setdefault('Pf', np.eye(6))
            track.setdefault('Pp', np.eye(6))
            track.setdefault('Sp', np.zeros((6, 1)))

            summary = {
                'Track ID': track['track_id'],
                'Number of Measurements': len(track['measurements']),
                'Hit Count': hit_counts.get(track['track_id'], 0),
                'Miss Count': miss_counts.get(track['track_id'], 0),
                'Current State': track['current_state'],
                'Time at Poss1': [],  # Add logic to fill these based on your conditions
                'Measurements at Poss1': [],
                'Time at Tent1': [],
                'Measurements at Tent1': [],
                'Time at Firm': [],
                'Measurements at Firm': [],
                'Measurement History': [m[0] for m in track['measurements']],
                'Track Status': 'occupied' if track['track_id'] in firm_ids else 'free',
                'Sf': track['Sf'].flatten(),
                'Sp': track['Sp'].flatten(),
                'Pp': track['Pp'].flatten(),
                'Pf': track['Pf'].flatten(),
            }

            # Output or process the summary as needed
            print(summary)

# Ensure to call the main function if this script is executed
if __name__ == "__main__":
    main()